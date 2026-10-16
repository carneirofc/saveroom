# Install using Standalone Images

> Any questions, problems or suggestions with this guide? Ask a question in our
> [issue tracker](https://github.com/carneirofc/baserow/issues) or contribute the change yourself at
> https://github.com/carneirofc/baserow/tree/develop/docs .

> Docker version 19.03 is the minimum required to build Saveroom. It is strongly
> advised however that you install the latest version of Docker available.
> Please check that your docker is up to date by running `docker -v`.

Saveroom consists of a number of services, two of which are built and provided as 
separate standalone images by us:
* `ghcr.io/carneirofc/baserow/backend:0.6.0` which by default starts the Gunicorn Django backend server 
  for Saveroom but is also used to start the celery workers and celery beat services.
* `ghcr.io/carneirofc/baserow/web-frontend:0.6.0` which is a Nuxt server providing Server Side rendering 
  for the website.

If you want to use your own container orchestration software like Kubernetes then these
images let you run and scale these different parts of Saveroom independently. 

For an example of how to use these images see the
[`docker-compose.yaml`](https://github.com/carneirofc/baserow/blob/develop/docker-compose.yaml) 
in the root of our repository. 

## All Services needed to run Saveroom

These are all the services you need to set up to run a Saveroom using the standalone 
images:

* `ghcr.io/carneirofc/baserow/backend:0.6.0` (default command is `gunicorn`)
* `ghcr.io/carneirofc/baserow/backend:0.6.0` with command `celery-worker`
* `ghcr.io/carneirofc/baserow/backend:0.6.0` with command `celery-exportworker`
* `ghcr.io/carneirofc/baserow/backend:0.6.0` with command `celery-beat`
* `ghcr.io/carneirofc/baserow/web-frontend:0.6.0` (default command is `nuxt-prod`)
* A postgres database 
* A redis server

## Configuration Caveats

* See [Configuring Saveroom](configuration.md) for specific details on the supported 
  environment variables.
* You must set `BASEROW_PUBLIC_URL` (usually only when behind your a reverse proxy, see 
  below for details) or `PUBLIC_BACKEND_URL` and `PUBLIC_WEB_FRONTEND_URL`
* You must set `PRIVATE_BACKEND_URL` so the web-frontend server can make direct 
  HTTP requests to the backend. The web-frontend might not have access to the 
  `PUBLIC_BACKEND_URL` or `BASEROW_PUBLIC_URL`, or there could be a more direct internal
  route it could use. (e.g. from container to container instead of via the internet). 
* These images do not come with a Caddy Reverse proxy and so the 
  `BASEROW_CADDY_ADDRESSES` environment variable used in other installation methods 
  has no affect.
* You must set a `SECRET_KEY` environment variable for the backend gunicorn server.
* See our example [`Caddyfile`](https://github.com/carneirofc/baserow/blob/develop/Caddyfile)
  for an example on how to setup a reverse proxy correctly with Saveroom. In summary you
  need to:
  * Redirect `/api/` and `/ws/` requests to the backend gunicorn service without 
    dropping these prefixes.
  * Serve the files in the `/baserow/media` folder in the backend gunicorn service 
    (share with your proxy using a volume) at the `/media` endpoint. Ensure all media
    responses have `X-Content-Type-Options: nosniff` and
    `Content-Security-Policy: sandbox; default-src 'none'; script-src 'none'; object-src 'none'; base-uri 'none'`.
    Requests with a `dl` query parameter can use
    `Content-Disposition: attachment; filename=THE_DL_QUERY_PARAM_VALUE`.
  * Send all other requests to the web-frontend service.
* You must provide all email related environment variables to both the backend and 
  celery-worker services. This is because the `celery-worker` service is the one 
  actually connecting via SMTP to send emails.
