from django.db import migrations

MCP_ENDPOINT_ACTION_TYPES = [
    "create_mcp_endpoint",
    "update_mcp_endpoint",
    "delete_mcp_endpoint",
]


def delete_mcp_endpoint_actions(apps, schema_editor):
    # The undo/redo history looks every action type up in the registry, so actions
    # of the removed types would fail to undo. The audit log keeps its own rendered
    # copy and stays untouched.
    Action = apps.get_model("core", "Action")
    Action.objects.filter(type__in=MCP_ENDPOINT_ACTION_TYPES).delete()


class Migration(migrations.Migration):
    """
    The MCP server is removed. Existing endpoints, and with them their URLs, are
    dropped.
    """

    dependencies = [
        ("core", "0126_alter_notification_workspace_and_more"),
    ]

    operations = [
        migrations.RunPython(
            delete_mcp_endpoint_actions, migrations.RunPython.noop
        ),
        migrations.DeleteModel(name="MCPEndpoint"),
    ]
