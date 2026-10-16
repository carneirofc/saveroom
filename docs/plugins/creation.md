# Creating a plugin

> Check out the [issue tracker](https://github.com/carneirofc/baserow/issues) for
> discussion.

In this guide we dive into how to create a Saveroom plugin from scratch, give you example
plugins to get inspiration from and discuss how to publish your plugin.

## Plugin Architecture

A Saveroom plugin is fundamentally a folder named after the plugin, containing a
`backend` and/or a `web-frontend` folder. Saveroom has two main services, a
Django `backend` API server and a Nuxt frontend
`web-frontend` server. A Saveroom plugin can plug into either both or just one of these
services by populating the respective plugin sub-folder.

Since the `backend` service is built with Django, the `backend` sub-folder in a plugin
should be a Django [app](https://docs.djangoproject.com/en/stable/ref/applications/).
Similarly, the `web-frontend` service is built using Nuxt.js, and so the `web-frontend`
plugin sub-folder should contain a Nuxt
[module](https://nuxt.com/docs/guide/going-further/modules).

### Plugin Installation API

> The current Saveroom Plugin API Version is `0.0.1-alpha`.

All the Saveroom official images ship with the following bash scripts which are used to
install plugins. They can be used either in a Dockerfile at build time to bake a plugin
into a Docker image or to install a plugin into an existing Saveroom container at
runtime.
`install_plugin.sh` can be used to install a plugin from an url, a git repo or a local
folder on the filesystem.

You can find these scripts in the following locations in our images:

1. `/baserow/plugins/install_plugin.sh`
2. `/baserow/plugins/uninstall_plugin.sh`
3. `/baserow/plugins/list_plugins.sh`

These scripts expect a Saveroom plugin to follow the conventions described below.

### Plugin File Structure

The `install_plugin.sh/uninstall_plugin.sh` scripts expect your plugin to have a
specific structure as follows:

```
├── plugin_name
│  ├── baserow_plugin_info.json (A simple json file containing info about your plugin)
│  ├── backend/ (Your plugins django app which will be installed into the backend)
│  │  ├── setup.py
│  │  ├── build.sh (Called when installing the plugin in a Dockerfile/container)
│  │  ├── runtime_setup.sh (Called on first runtime startup of the plugin)
│  │  ├── uninstall.sh (Called when uninstalling the plugin in a container)
│  │  ├── src/plugin_name/src/config/settings/settings.py (Optional Django setting file)
│  ├── web-frontend/ (Your plugins nuxt module which will be installed into the web-frontend)
│  │  ├── package.json
│  │  ├── build.sh (Called when installing the plugin in a Dockerfile/container)
│  │  ├── runtime_setup.sh (Called on first runtime startup of the plugin)
│  │  ├── uninstall.sh (Called when uninstalling the plugin in a container)
│  │  ├── modules/plugin-name/module.js (Your plugins module file)
```

The backend and web-frontend sub folders come with three bash files which will be
automatically called by Saveroom's plugin scripts during installation and uninstallation.
You can use these scripts to perform extra build steps, installation of packages, and
other docker container build steps required.

1. `build.sh`: Called when a plugin is built into a Dockerfile, or on container startup
   if a runtime installation is occurring.
2. `runtime_setup.sh`: Called when the first time a container starts up after the plugin
   has been installed, useful for running superuser commands on the embedded database if
   it exists.
3. `uninstall.sh` Called on uninstall, the database will be available and so any
   backwards migrations should be run here.

### The plugin info file

The `baserow_plugin_info.json` file is a json file, in your root plugin folder,
containing metadata about your plugin. It should have the following JSON structure:

```json
{
  "name": "TODO",
  "version": "TODO",
  "supported_baserow_versions": "2.3.2",
  "plugin_api_version": "0.0.1-alpha",
  "description": "TODO",
  "author": "TODO",
  "author_url": "TODO",
  "url": "TODO",
  "license": "TODO",
  "contact": "TODO"
}
```

### Expected plugin structure when installing --url or --git

When using `install_plugin.sh --url URL_TO_PLUGIN_TAR_GZ`
or `install_plugin.sh --git URL_TO_PLUGIN_REPO` the plugin archive/repo should contain a
single `plugins` folder, inside which there should a single plugin folder following the
structure above and has the same name as your plugin. For example a conforming tar.gz archive should contain something like:

```
├─ * (an outermost wrapper directory named anything is allowed but not required) 
│  ├── plugins/ 
│  │  ├── plugin_name/
│  │  │  ├── baserow_plugin_info.json 
│  │  │  ├── backend/
│  │  │  ├── web-frontend/
```

## Writing a Plugin

Now you have created a plugin, lets go into more detail of how to actually extend and
customize Saveroom using your plugin.

First you should read the following documentation for a basic introduction to Saveroom's
technical architecture:

1. [Architecture](../architecture.md)
2. [Database Plugin](../technical/database-plugin.md)

### Storing State

If your plugin needs to store state, you should only ever do this in:

1. The database being used by Baserow
2. Using Django's default storage mechanism
3. The Redis being used by Saveroom but only for non-persistent state like a cache that
   is fine to be destroyed at any moment.

**Never store any state in your plugin folder itself inside the container.** This folder
is deleted and recreated as part of the plugin installation process and any state you
store inside it can be lost.

### Writing a Backend Plugin

#### Adding Python Requirements

Your backend plugin is just a normal python module which will be installed into the
Saveroom virtual environment using `pip` by `install_plugin.sh`. Declare your python requirements in your
plugin's own requirements file.

#### As a Django App

When the Saveroom backend Django service starts up it looks for any plugins in the plugin
directory which have a `backend` sub-folder. If it finds any it assumes
the `backend/src/plugin_name/`
sub folder contains a Django App and adds it to the `INSTALLED_APPS`. This means that
your backend plugin must be a Django app whose name exactly matches the name of the
plugin folder.

In your plugin's Django app you can do anything that you normally can do with a Django
app such as having migrations, using the `ready()` method to do startup configuration
etc.

#### Backend Registries

Saveroom has a number of registries which are used to dynamically configure Saveroom. For
example the `field_type_registry` contains various implementations of the `FieldType`
class.

Each registry contains various implementations of a particular "interface" class. A
registry in Saveroom is simply a singleton dictionary populated by apps in their `ready`
method. Then Saveroom's various API endpoints will use these registries at runtime.

So in your plugin's Django Apps `ready` method is where you should import any relevant
registries and register your own implementations of field types.

For example, the `plugin_registry` is used to register implementations of the
`baserow.core.registries.Plugin` interface. You can create your own class which
implements this base class and register it with the `plugin_registry` by:

```python
from baserow.core.registries import plugin_registry
from django.apps import AppConfig


class PluginNameConfig(AppConfig):
    name = "my_baserow_plugin"

    def ready(self):
        from .plugins import PluginNamePlugin

        plugin_registry.register(PluginNamePlugin())
```

You can see all the different things you can dynamically register into Saveroom with your
plugin by searching the Saveroom codebase and inspecting the `registry.py` and
`registries.py` files.

### Writing a Web Frontend Plugin

#### Adding Node Requirements

Your web-frontend plugin is just a normal node package which will be installed into
Saveroom's node_modules using `yarn` by `install_plugin.sh`. You can add any extra
frontend requires to your `web-frontend/package.json`.

#### Web-frontend Registries

The Saveroom web-frontend nuxt app also follows the registry pattern that the backend
has. This means it has an equivalent frontend registry for most backend registries where
it makes sense. So if you were to registry a new field type in the backend registry then
also make sure to registry a new field type in the frontend registry also.

## Publishing your Plugin

The easiest way to share you plugin with others is by making a public git repository
using GitLab, GitHub or some other git host. Once you have pushed your plugin folder to
the git repository then anyone can then install your plugin following the steps in
the [Plugin Installation](./installation.md) guide.

Also, please share and post about your plugin on
the [issue tracker](https://github.com/carneirofc/baserow/issues)!

## Further Reading

Check out the following guides in the plugin section which go into more specifics on say
creating a new field type:

1. [Application Type Guide](./application-type.md)
1. [Field Type Guide](./field-type.md)
1. [Field Converter Guide](./field-converter.md)
1. [View Type Guide](./view-type.md)
1. [View Filter Type Guide](./view-filter-type.md)
