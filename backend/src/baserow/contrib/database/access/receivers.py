from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import DatabaseAccessGrant
from .resolver import invalidate_workspace_grants_cache


@receiver(post_save, sender=DatabaseAccessGrant)
@receiver(post_delete, sender=DatabaseAccessGrant)
def invalidate_grants_cache(sender, instance, **kwargs):
    """
    Keeps the "workspace has grants" cache honest for every write path, including
    cascading deletes of tables, databases, teams and users.
    """

    workspace_id = instance.workspace_id
    invalidate_workspace_grants_cache(workspace_id)
    transaction.on_commit(lambda: invalidate_workspace_grants_cache(workspace_id))
