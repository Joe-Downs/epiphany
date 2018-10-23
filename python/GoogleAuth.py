#!/usr/bin/env python3

import httplib2
import json
import time
import os

from apiclient.discovery import build
from oauth2client import tools
from oauth2client.file import Storage
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import OAuth2WebServerFlow

#-------------------------------------------------------------------

# Globals
doc_mime_type = 'application/vnd.google-apps.document';
sheet_mime_type = 'application/vnd.google-apps.spreadsheet';
folder_mime_type = 'application/vnd.google-apps.folder'

# JMS this is probably a lie, but it's useful for comparisons
team_drive_mime_type = 'application/vnd.google-apps.team_drive'

# JMS Should these really be globals?
app_cred_file = 'client_id.json'
default_user_cred_file = 'user-credentials.json'
user_agent = 'gxcopy'

# Scopes documented here:
# https://developers.google.com/drive/v3/web/about-auth
scopes = {
    'drive' : 'https://www.googleapis.com/auth/drive',
    'admin' : 'https://www.googleapis.com/auth/admin.directory.group',
    'group' : 'https://www.googleapis.com/auth/apps.groups.settings',
}

#-------------------------------------------------------------------

def _load_app_credentials(app_cred_file, log=None):
    # Read in the JSON file to get the client ID and client secret
    cwd  = os.getcwd()
    file = os.path.join(cwd, app_cred_file)
    if not os.path.isfile(file):
        log.error("Error: JSON file {0} does not exist".format(file))
        exit(1)
    if not os.access(file, os.R_OK):
        log.error("Error: JSON file {0} is not readable".format(file))
        exit(1)

    with open(file) as data_file:
        app_cred = json.load(data_file)

    if log:
        log.debug('Loaded application credentials from {0}'
                  .format(file))

    return app_cred

def _load_user_credentials(scope, app_cred,
                           user_cred_file=default_user_cred_file, log=None):
    # Get user consent
    client_id       = app_cred['installed']['client_id']
    client_secret   = app_cred['installed']['client_secret']
    flow            = OAuth2WebServerFlow(client_id, client_secret, scope)
    flow.user_agent = user_agent

    storage   = Storage(user_cred_file)
    user_cred = storage.get()

    # If no credentials are able to be loaded, fire up a web
    # browser to get a user login, etc.  Then save those
    # credentials in the file listed above so that next time we
    # run, those credentials are available.
    if user_cred is None or user_cred.invalid:
        user_cred = tools.run_flow(flow, storage,
                                   tools.argparser.parse_args())

    if log:
        log.debug('Loaded user credentials from {0}'
                  .format(user_cred_file))

    return user_cred

def _authorize_user(user_cred, name, version, log=None):
    http    = httplib2.Http()
    http    = user_cred.authorize(http)
    service = build(name, version, http=http)

    if log:
        log.info('OAuth authorized to Google: {name} / {version}'
                 .format(name=name, version=version))

    return service

#-------------------------------------------------------------------

def service_oauth_login(scope, api_name, api_version,
                        app_json, user_json,
                        gauth_max_attempts=3, log=None):
    # Put a loop around this so that it can re-authenticate via the
    # OAuth refresh token when possible.  Real errors will cause the
    # script to abort, which will notify a human to fix whatever the
    # problem was.
    auth_count = 0
    while auth_count < gauth_max_attempts:
        try:
            # Authorize the app and provide user consent to Google
            app_cred  = _load_app_credentials(app_json)
            user_cred = _load_user_credentials(scope, app_cred, user_json)
            service   = _authorize_user(user_cred, api_name, api_version, log=log)
            break

        except AccessTokenRefreshError:
            # The AccessTokenRefreshError exception is raised if the
            # credentials have been revoked by the user or they have
            # expired.
            log.error("Failed to authenticate to Google (will sleep and try again)")

            # Delay a little and try to authenticate again
            time.sleep(10)

        auth_count = auth_count + 1

    if auth_count > gauth_max_attempts:
        message = ("Failed to authenticate to Google {num} times.  A human needs to figure this out."
                   .format(num=gauth_max_attempts))
        log.error(message)
        email_and_die(message)

    return service

#===================================================================

def service_api_key(api_name, api_version, api_key_filename, log=None):
    if not os.path.exists(api_key_filename):
        print('ERROR: The file {f} does not exist'
              .format(f=api_key_filename), file=os.stderr)
        exit(1)

    with open(api_key_filename) as f:
        key = f.read().strip()

    if log:
        log.info("Got key: {key}".format(key=key))

    # JMS Do we need to give http to service?
    service = build(api_name, api_version, developerKey=key)

    if log:
        log.info('API key authorized to Google: {name} / {version}'
                 .format(name=api_name, version=api_version))

    return service