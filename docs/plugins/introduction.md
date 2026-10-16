# Introduction

Saveroom plugins let you fully customize and extend Saveroom quickly and easily. Multiple
plugins can be installed into a new or existing Saveroom installation, they get full
access to Saveroom's internals for maximum customization and are straightforward develop
and publish.

Some examples of what you can do with a Saveroom plugin are:

* Add new Saveroom:
    * Field Types
    * View Types/Filters/Sorts/Decorations/Aggregations
    * Formula Functions/Types
* Add or customize pages, components, styling
* Integrate with 3rd party APIs or software
* Install custom postgres extensions, system packages, python and node dependencies
* And much more!

Saveroom Plugins are only available for self-hosted installations currently and are 
**experimental** and subject to change.

1. **You should always make backups of your Saveroom data before installing and using any
   plugin.**
2. **You should only ever install plugins from a trusted source.**
3. **Saveroom is not responsible for and does not officially support any plugins
   currently, installing and using them is entirely at your own risk.**

## Installing a Plugin

The [Plugin Installation](./installation.md) guide goes into detail on how to install
and uninstall Saveroom plugins in the various official Saveroom docker images.

Currently, we do not provide an officially supported plugins, however check out the
[issue tracker](https://github.com/carneirofc/baserow/issues) for further discussion.

## Creating a plugin

See [creating a plugin](./creation.md) for the folder layout a plugin needs and how
to install it.

## Creating a Plugin

Finally, the [Plugin Creation](./creation.md) guide explains in more detail how to
create your own plugins and publish them for others to use.

