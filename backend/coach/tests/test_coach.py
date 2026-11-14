from datetime import timedelta, timezone as datetime_timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from monitoring.models import Building, Meter, EnergyReading
from coach.models import AIRecommendation, LLMRequestLog, RecommendationFeedback
from coach.serializers import RecommendationFeedbackSerializer


@patch.dict('os.environ', {'OPENAI_API_KEY': ''})
class CoachAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='coach_testuser', password='password123')
        self.client.force_authenticate(user=self.user)
        self.building = Building.objects.create(
            name="Test Engineering Lab",
            location="Room E101",
            area_sqm=2000.0,
            baseline_kwh_per_day=300.0, has_solar_installation=False
        )
        self.meter = Meter.objects.create(
            building=self.building,
            device_id="TEST-ENG-01",
            meter_type="ELECTRICITY"
        )
        # Two complete, explicitly hourly UTC days; one point is insufficient.
        start = (timezone.now().astimezone(datetime_timezone.utc)
                 .replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2))
        EnergyReading.objects.bulk_create([
            EnergyReading(meter=self.meter, timestamp=start + timedelta(hours=i),
                          energy_kwh=5, power_kw=35, interval_seconds=3600)
            for i in range(48)
        ])

    def test_forecast_endpoint(self):
        url = reverse('building-forecast', kwargs={'building_id': self.building.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['building_id'], self.building.id)
        self.assertEqual(response.data['horizon_days'], 7)
        self.assertEqual(len(response.data['forecast']), 7)
        self.assertIn('predicted_kwh', response.data['forecast'][0])

    def test_recommendation_generate_endpoint(self):
        url = reverse('recommendations-generate')
        payload = {
            'building_id': self.building.id,
            'target_savings_pct': 15.0
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('recommendations', response.data)
        self.assertGreaterEqual(len(response.data['recommendations']), 1)
        self.assertIn('sustainability_assessment', response.data)
        self.assertIn('engine_telemetry', response.data)
        self.assertIn('sustainability_score', response.data['sustainability_assessment'])
        self.assertTrue(AIRecommendation.objects.filter(building=self.building).exists())
        self.assertTrue(LLMRequestLog.objects.exists())

    def test_recommendation_list_and_building_filter(self):
        other = Building.objects.create(name="Other Building", has_solar_installation=False)
        rec1 = AIRecommendation.objects.create(
            building=self.building, title="Rec 1", suggested_action="Do A"
        )
        rec2 = AIRecommendation.objects.create(
            building=other, title="Rec 2", suggested_action="Do B"
        )
        url = reverse('recommendation-list')

        all_resp = self.client.get(url)
        self.assertEqual(all_resp.status_code, status.HTTP_200_OK)
        self.assertEqual({r['id'] for r in all_resp.data['results']}, {rec1.id, rec2.id})

        filtered = self.client.get(url, {'building_id': self.building.id})
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        self.assertEqual([r['id'] for r in filtered.data['results']], [rec1.id])

        empty = self.client.get(url, {'building_id': -1})
        self.assertEqual(empty.status_code, status.HTTP_200_OK)
        self.assertEqual(empty.data['results'], [])

        invalid = self.client.get(url, {'building_id': 'not-an-int'})
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feedback_binds_url_recommendation_and_allows_matching_body(self):
        rec = AIRecommendation.objects.create(
            building=self.building, title="Peak Shave", suggested_action="Shift load"
        )
        other_rec = AIRecommendation.objects.create(
            building=self.building, title="HVAC Setback", suggested_action="Adjust setpoint"
        )
        url = reverse('recommendation-feedback', kwargs={'pk': rec.id})

        without_body_id = self.client.post(
            url, {'rating': 4, 'is_accepted': True, 'comment': 'Helpful'}, format='json'
        )
        self.assertEqual(without_body_id.status_code, status.HTTP_201_CREATED)
        self.assertEqual(without_body_id.data['recommendation'], rec.id)
        self.assertEqual(
            RecommendationFeedback.objects.get(pk=without_body_id.data['id']).recommendation_id,
            rec.id,
        )

        duplicate_by_same_user = self.client.post(
            url, {'rating': 5, 'comment': 'Second try'}, format='json'
        )
        self.assertEqual(duplicate_by_same_user.status_code, status.HTTP_400_BAD_REQUEST)

        other_url = reverse('recommendation-feedback', kwargs={'pk': other_rec.id})
        with_matching_id = self.client.post(
            other_url, {'recommendation': other_rec.id, 'rating': 5}, format='json'
        )
        self.assertEqual(with_matching_id.status_code, status.HTTP_201_CREATED)
        self.assertEqual(with_matching_id.data['recommendation'], other_rec.id)

        mismatched = self.client.post(
            url, {'recommendation': other_rec.id, 'rating': 5}, format='json'
        )
        self.assertEqual(mismatched.status_code, status.HTTP_400_BAD_REQUEST)

        missing = self.client.post(
            reverse('recommendation-feedback', kwargs={'pk': 999999}),
            {'rating': 5},
            format='json',
        )
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

    def test_feedback_rating_validation(self):
        rec = AIRecommendation.objects.create(
            building=self.building, title="Lighting", suggested_action="Dim corridors"
        )
        url = reverse('recommendation-feedback', kwargs={'pk': rec.id})

        for valid_rating in (1, 5):
            with self.subTest(valid_rating=valid_rating):
                RecommendationFeedback.objects.filter(recommendation=rec).delete()
                resp = self.client.post(url, {'rating': valid_rating}, format='json')
                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        RecommendationFeedback.objects.filter(recommendation=rec).delete()

        for invalid_rating in (-1, 0, 6):
            with self.subTest(invalid_rating=invalid_rating):
                resp = self.client.post(url, {'rating': invalid_rating}, format='json')
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                with self.assertRaises(ValidationError):
                    RecommendationFeedback(recommendation=rec, rating=invalid_rating).full_clean()

        serializer = RecommendationFeedbackSerializer(data={'rating': 4})
        self.assertFalse(serializer.is_valid())
        self.assertIn('recommendation', serializer.errors)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('recommendation-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_recommendation_includes_multiple_user_feedbacks(self):
        User = get_user_model()
        second_user = User.objects.create_user(username='teammate_2', password='password123')
        rec = AIRecommendation.objects.create(
            building=self.building, title="Night HVAC Setback", suggested_action="Lower night setpoint by 2C"
        )
        fb_url = reverse('recommendation-feedback', kwargs={'pk': rec.id})

        self.client.post(fb_url, {'rating': 5, 'is_accepted': True, 'comment': 'Works well in winter'}, format='json')
        self.client.force_authenticate(user=second_user)
        self.client.post(fb_url, {'rating': 3, 'is_accepted': False, 'comment': 'Need lab schedule check'}, format='json')

        list_resp = self.client.get(reverse('recommendation-list'), {'building_id': self.building.id})
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        feedbacks = list_resp.data['results'][0]['feedback']
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(feedbacks[0]['user_username'], 'teammate_2')
        self.assertEqual(feedbacks[0]['rating'], 3)
        self.assertEqual(feedbacks[0]['comment'], 'Need lab schedule check')
        self.assertEqual(feedbacks[1]['user_username'], 'coach_testuser')
        self.assertEqual(feedbacks[1]['rating'], 5)
        self.assertEqual(feedbacks[1]['comment'], 'Works well in winter')
