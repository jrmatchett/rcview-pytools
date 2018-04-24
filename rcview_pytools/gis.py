"""Classes for creating a GIS object connected to the RC View Portal."""

from arcgis import GIS as _GIS
from arcgis._impl.portalpy import Portal as _Portal
from arcgis._impl.connection import _ArcGISConnection, _normalize_url, _parse_hostname
import arcgis.env as _arcgis_env
from six.moves.urllib_parse import urlencode as _urlencode
import tempfile as _tempfile
from selenium import webdriver as _webdriver
from selenium.webdriver.chrome.options import Options as _Options
from selenium.webdriver.support.ui import WebDriverWait as _WebDriverWait
from selenium.webdriver.support import expected_conditions as _EC
from selenium.webdriver.common.by import By as _By
from selenium.common.exceptions import TimeoutException as _TimeoutException
try:
    import keyring as _keyring
    _has_keyring = True
except:
    _has_keyring = False

_print_messages = True


class RCViewGIS(_GIS):
    """An arcgis GIS object connected to the RC View Portal."""
    def __init__(self, email, password='use_keyring', keyring_name='RCView',
                 client_id='5Mp8pYtrnog7vMWb', verbose=True):
        """Construct an arcgis GIS object for the RC View Portal.

        The selenium python package and the ChromeDriver application must be
        installed to use this class
        (see https://sites.google.com/a/chromium.org/chromedriver/getting-started
        for installation instructions). This class can also use a password
        stored on the operating system keychain (requires the keyring python
        package, which is installed with arcgis version 1.4). To setup a login
        keyring, run:

        import keyring
        keyring.set_password('RCView', 'user_email', 'user_password')

        Arguments:
        email         Red Cross single-sign-on email.
        password      Red Cross single-sign-on password. 'use_keyring' will
                      retrieve password from the system keychain.
        keyring_name  Name of the password keyring.
        client_id     Client ID (aka App ID) of a RC View Portal application.
        verbose       Prints login messages.
        """
        global _print_messages
        _print_messages = verbose

        if _print_messages:
            print('Logging into RC View...', end='', flush=True)

        from arcgis._impl.tools import _Tools

        self._url = 'https://maps.rcview.redcross.org/portal'
        self._username = email
        if _has_keyring and password == 'use_keyring':
            self._password = _keyring.get_password(keyring_name, email)
        else:
            self._password = password if not password == 'use_keyring' else None
        if not self._password:
            raise ValueError('Unable to set password. Please check the email, password, and keyring_name.')
        self._client_id = client_id
        self._key_file = None
        self._cert_file = None
        self._portal = None
        self._con = None
        self._verify_cert = None
        self._datastores_list = None
        self._portal = _RCViewPortal(
            url=self._url, username=self._username,
            password=self._password, client_id=self._client_id)
        self._con = self._portal.con
        self._tools = _Tools(self)

        _arcgis_env.active_gis = self

        if _print_messages:
            print('success.', flush=True)


class _RCViewPortal(_Portal):
    # A Portal object for RC View.
    def __init__(self, url, username, password, client_id, key_file=None,
                 cert_file=None, expiration=60, referer=None, proxy_host=None,
                 proxy_port=None, connection=None,
                 workdir=_tempfile.gettempdir(), tokenurl=None,
                 verify_cert=True):

        if _print_messages:
            print('connecting to portal...', end='', flush=True)

        self.hostname = _parse_hostname(url)
        self.workdir = workdir
        self.url = url
        self.resturl = url + '/sharing/rest/'
        self._basepostdata = {'f': 'json'}
        self._version = None
        self._properties = None
        self._resources = None
        self._languages = None
        self._regions = None
        self._is_pre_162 = False
        self._is_pre_21 = False

        self.con = _RCViewConnection(baseurl=self.resturl,
                                     tokenurl=tokenurl,
                                     username=username,
                                     password=password,
                                     key_file=key_file,
                                     cert_file=cert_file,
                                     expiration=expiration,
                                     all_ssl=True,
                                     referer=referer,
                                     proxy_host=proxy_host,
                                     proxy_port=proxy_port,
                                     verify_cert=verify_cert,
                                     client_id=client_id)
        self.get_properties(True)


class _RCViewConnection(_ArcGISConnection):
    def oauth_authenticate(self, client_id, expiration):
        # Authenticate with RC View single-sign-on.
        if _print_messages:
            print('authenticating...', end='', flush=True)

        parameters = {
            'client_id': client_id,
            'response_type': 'code',
            'expiration': -1,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }

        url = self.baseurl + 'oauth2/authorize'
        paramstring = _urlencode(parameters)
        codeurl = "{}?{}".format(url, paramstring)

        options = _Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        driver = _webdriver.Chrome(chrome_options=options)
        driver.get(codeurl)

        delay = 10
        try:
            using_redcross_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'idp_Name')))
        except _TimeoutException:
            driver.quit()
            print('Accessing Red Cross single-sign-on took too much time.')

        using_redcross_element.click()

        try:
            username_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'ssologin-username')))
            password_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'ssologin-password')))
            signin_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'signin')))
        except _TimeoutException:
            driver.quit()
            print('Accessing Red Cross single-sign-on took too much time.')

        username_element.send_keys(self._username)
        password_element.send_keys(self._password)
        signin_element.click()

        try:
            code_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'code')))
        except _TimeoutException:
            driver.quit()
            print('Receiving an authentication code took too much time.')

        code = code_element.get_attribute('value')
        driver.quit()

        parameters = {
            'client_id': client_id,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }

        token_info = self.post('oauth2/token', parameters, ssl=True,
                               add_token=False)
        self._refresh_token = token_info['refresh_token']
        self._token = token_info['access_token']
        return self._token
