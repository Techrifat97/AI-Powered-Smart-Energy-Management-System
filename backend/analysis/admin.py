from django.contrib import admin
from .models import TariffPlan, EnergyAlert, CostReport


@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'rate_standard_eur_per_kwh', 'rate_peak_eur_per_kwh', 'is_active', 'created_at')
    list_filter = ('is_active',)


@admin.register(EnergyAlert)
class EnergyAlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'building', 'severity', 'alert_type', 'is_resolved', 'created_at')
    list_filter = ('severity', 'alert_type', 'is_resolved', 'building')
    search_fields = ('message', 'building__name')


@admin.register(CostReport)
class CostReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'building', 'period_start', 'period_end', 'total_cost_eur', 'created_at')
    list_filter = ('building',)

