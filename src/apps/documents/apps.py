from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documentos e termos"

    def ready(self):
        from apps.core import events

        from .services import cancel_for_reversed_operation

        events.subscribe(events.OPERATION_REVERSED, cancel_for_reversed_operation)
