from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = "apps.alerts"
    label = "alerts"
    verbose_name = "Alertas de estoque"

    def ready(self):
        from apps.core import events

        from .services import evaluate_consumables

        events.subscribe(events.CONSUMABLES_CHANGED, evaluate_consumables)
