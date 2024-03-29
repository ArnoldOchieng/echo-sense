import sys, logging, traceback, os
import webapp2
from webapp2_extras import jinja2
from datetime import datetime
from google.appengine.api import memcache, mail
from google.appengine.ext.webapp import blobstore_handlers
from common import my_filters
from webapp2_extras import sessions
import logging
import tools
from constants import *
import json

def jinja2_factory(app):
    j = jinja2.Jinja2(app)
    j.environment.filters.update({
        'printjson': my_filters.printjson
    })
    j.environment.tests.update({
        })
    # j.package_path = 'views/templates'
    j.environment.globals.update({
        # Set global variables.
        'uri_for': webapp2.uri_for,
        # ...
    })
    return j

class BaseRequestHandler(webapp2.RequestHandler):
    def __init__(self, request, response):
        super(BaseRequestHandler, self).__init__(request, response)
        self.enterprise = None
        self.user = None

    @webapp2.cached_property
    def jinja2(self):
        return jinja2.get_jinja2(factory=jinja2_factory)

    def render_template(self, filename, **template_args):
        self.response.write(self.jinja2.render_template(filename, **template_args))

    def json_out(self, data=None, error=0, message=None, status=None, success=True, debug=False):
        message = message if message else ERROR.LABELS.get(error)
        if not message:
            message = "Unknown"
        if not error and not success:
            error = ERROR.OTHER
        out = {
            'success': error == 0,
            'code': error,
            'message': message,
            'data': data
        }
        _status = status if status else 200
        log_call = not self.session
        if log_call:
            from models import APILog
            success = False
            message = None
            APILog.Create(self.request, user=self.user, enterprise=self.enterprise,
                          status=_status, success=success, message=message)
        if debug or DEBUG_API:
            logging.debug(out)
        self.response.write(json.dumps(out))
        self.response.set_status(_status)

    def process_exception(self, suppressed_exceptions=None):
        exception_name = sys.exc_info()[0].__name__
        exception_details = str(sys.exc_info()[1])
        exception_traceback = ''.join(traceback.format_exception(*sys.exc_info()))
        logging.error(exception_traceback)
        send_email = not (suppressed_exceptions and exception_name in suppressed_exceptions)
        if send_email:
            exception_expiration = 3600 # seconds (max 1 mail per hour for a particular exception)
            mail_admin = SENDER_EMAIL # must be admin for the application
            sitename = SITENAME
            ver = os.environ['CURRENT_VERSION_ID']
            dev = any(keyword in ver for keyword in TEST_VERSIONS) or tools.on_dev_server()
            sitename += ":DEV" if dev else ":PROD"
            session = self.session
            ename = "Unknown Org"
            if session and session.has_key('enterprise'):
                ename = session['enterprise'].name
            throttle_name = 'exception-' + exception_name
            throttle = memcache.get(throttle_name)
            if throttle is None and not dev:
                memcache.add(throttle_name, 1, exception_expiration)
                subject = '[%s] exception for %s [%s: %s]' % (sitename, ename, exception_name, exception_details)
                body = exception_traceback + "\n\n" + self.request.uri
                mail.send_mail(to=ERROR_EMAIL, sender=mail_admin,
                               subject=subject,
                               body=body)
        return exception_name, exception_details, exception_traceback

    def handle_exception(self, exception, debug_mode):
        exception_name, exception_details, exception_traceback = self.process_exception()
        template_values = {
            'pg_title': "Error",
            'SITENAME':SITENAME,
            'COMPANY_NAME': COMPANY_NAME,
            'YEAR':datetime.now().year,
            'CURTIME': datetime.now(),
            'GA_ID': GA_ID
        }
        if self.session.has_key('user') and self.session['user'].is_admin():
            template_values['traceback'] = exception_traceback
        self.render_template("error.html", ** template_values)

    def dispatch(self):
        # Get a session store for this request.
        self.session_store = sessions.get_store(request=self.request)

        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    MESSAGE_KEY = '_flash_message'
    def add_message(self, message, level=UI.INFO):
       self.session.add_flash(message, level, BaseRequestHandler.MESSAGE_KEY)

    def get_messages(self):
       return self.session.get_flashes(BaseRequestHandler.MESSAGE_KEY)

    @webapp2.cached_property
    def session(self):
        # Returns a session using the default cookie key.
        return self.session_store.get_session(backend="datastore")

class JsonRequestHandler(BaseRequestHandler):

    def handle_exception(self, exception, debug_mode):
        DeadlineExceededError = "DeadlineExceededError"
        HTTPUnauthorized = "HTTPUnauthorized"
        APIError = "APIError"
        exception_name, exception_details, exception_traceback = self.process_exception(suppressed_exceptions=[HTTPUnauthorized, APIError])
        error_messages = {
            DeadlineExceededError: "The request took too long to process.",
            HTTPUnauthorized: "Request error, please try again", #invalid CSRF token in ajax
            APIError: exception_details
        }
        if exception_name in error_messages:
            self.json_out(message=error_messages[exception_name], success=False)
        else:
            self.json_out(message=exception_name, success=False)


class BaseUploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    session_store = None

    def add_message(self, level, message):
        self.session.add_flash(message, level, BaseHandler.MESSAGE_KEY)
        self.store()

    def store(self):
        self.session_store.save_sessions(self.response)

    def json_out(self, data=None, error=0, message=None, status=None, success=True, debug=False):
        message = message if message else ERROR.LABELS.get(error)
        if not message:
            message = "Unknown"
        if not error and not success:
            error = ERROR.OTHER
        out = {
            'success': error == 0,
            'code': error,
            'message': message,
            'data': data
        }
        if debug or DEBUG_API:
            logging.debug(out)
        self.response.write(json.dumps(out))
        self.response.set_status(status if status else 200)

    def dispatch(self):
        # Get a session store for this request.
        self.session_store = sessions.get_store(request=self.request)

        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session(backend="datastore")