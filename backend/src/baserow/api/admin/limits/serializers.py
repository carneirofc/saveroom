from rest_framework import serializers


class AdminOperationalLimitsSerializer(serializers.Serializer):
    """
    The retention and time limits the instance runs with. They come from Django
    settings, which are populated from the environment, so they are read-only
    here: changing one means changing the environment and restarting.
    """

    hours_until_trash_permanently_deleted = serializers.IntegerField()
    export_file_expire_minutes = serializers.IntegerField()
    snapshot_expiration_time_days = serializers.IntegerField()
    max_snapshots_per_workspace = serializers.IntegerField()
    user_log_entry_retention_days = serializers.IntegerField()
    row_history_retention_days = serializers.IntegerField()
    job_soft_time_limit_seconds = serializers.IntegerField()
    job_expiration_time_limit_minutes = serializers.IntegerField()
    import_export_resource_removal_after_days = serializers.IntegerField()
