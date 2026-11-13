from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from coach.models import AIRecommendation, RecommendationFeedback
from monitoring.models import Building

User = get_user_model()


class AccountsApiTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@smartenergy.local',
            password='admin123'
        )
        self.token_url = reverse('token_obtain_pair')
        self.users_url = reverse('user-list-create')
        self.me_url = reverse('current-user')

    def test_obtain_jwt_token_with_valid_credentials(self):
        response = self.client.post(self.token_url, {
            'username': 'admin',
            'password': 'admin123'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_obtain_jwt_token_with_invalid_credentials(self):
        response = self.client.post(self.token_url, {
            'username': 'admin',
            'password': 'wrongpassword'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_users_list_requires_authentication(self):
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_list_users(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Results are paginated by default
        results = response.data['results'] if 'results' in response.data else response.data
        usernames = [u['username'] for u in results]
        self.assertIn('admin', usernames)

    def test_authenticated_user_can_create_new_user(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'username': 'prof_evaluator',
            'email': 'prof@fh-dortmund.de',
            'password': 'evaluatorpass123',
            'first_name': 'Professor',
            'last_name': 'Evaluator'
        }
        response = self.client.post(self.users_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'prof_evaluator')
        self.assertEqual(response.data['email'], 'prof@fh-dortmund.de')
        self.assertNotIn('password', response.data)

        # Verify password was hashed and user can authenticate
        new_user = User.objects.get(username='prof_evaluator')
        self.assertTrue(new_user.check_password('evaluatorpass123'))

    def test_create_user_requires_password(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'username': 'student_user',
            'email': 'student@fh-dortmund.de',
            'first_name': 'Student'
        }
        response = self.client.post(self.users_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_create_user_with_duplicate_username_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'username': 'admin',
            'email': 'duplicate@smartenergy.local',
            'password': 'newpassword123'
        }
        response = self.client.post(self.users_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_current_user_profile_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'admin')
        self.assertEqual(response.data['email'], 'admin@smartenergy.local')

    def test_authenticated_recommendation_feedback_binds_to_user(self):
        building = Building.objects.create(name='Test Building', baseline_kwh_per_day=100.0)
        recommendation = AIRecommendation.objects.create(
            building=building,
            title='Peak Shaving Action',
            suggested_action='Reduce peak chiller setpoint',
            estimated_savings_kwh=25.0
        )
        url = reverse('recommendation-feedback', kwargs={'pk': recommendation.pk})

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(url, {
            'rating': 5,
            'is_accepted': True,
            'comment': 'Validated by admin'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user_username'], 'admin')

        feedback = RecommendationFeedback.objects.get(pk=response.data['id'])
        self.assertEqual(feedback.user, self.admin_user)
