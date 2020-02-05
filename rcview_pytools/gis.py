"""Classes for creating a GIS object connected to the RC View Portal."""

from arcgis import GIS as _GIS
from arcgis._impl.portalpy import Portal as _Portal
from arcgis._impl.connection import _ArcGISConnection, _normalize_url, _parse_hostname
import arcgis.env as _arcgis_env
from arcgis.geocoding import Geocoder as _Geocoder
from arcgis.features import FeatureSet as _FeatureSet
from arcgis.geometry import Geometry as _Geometry
from six.moves.urllib_parse import urlencode as _urlencode
import copy as _copy
import tempfile as _tempfile
from selenium import webdriver as _webdriver
from selenium.webdriver.chrome.options import Options as _Options
from selenium.webdriver.support.ui import WebDriverWait as _WebDriverWait
from selenium.webdriver.support import expected_conditions as _EC
from selenium.webdriver.common.by import By as _By
from selenium.common.exceptions import TimeoutException as _TimeoutException
import keyring as _keyring
from .extras import RCActivityIndicator as _RCSpinner

_print_messages = True


class RCViewGIS(_GIS):
    """An arcgis GIS object connected to the RC View Portal."""
    def __init__(self, email, password='use_keyring', client_id=None,
                 keyring_name='RCView', tokens_file=None,
                 tokens=None, verbose=True):
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
        tokens_file   (optional) A file containing the access tokens from a
                      previous login (created using the save_tokens method).
                      Reusing previous tokens skips the full authentication
                      process.
        tokens        (optional) A dictionary containing access tokens, having
                      keys RCVIEW_TOKEN and RCVIEW_REFRESH with values for
                      the token and refresh token, respectively.
        verbose       Prints login status messages.
        """
        global _print_messages
        _print_messages = verbose

        if _print_messages:
            self._spinner = _RCSpinner('Logging into RC View')
            self._spinner.start()
        else:
            self._spinner=None

        from arcgis._impl.tools import _Tools

        self._url = 'https://maps.rcview.redcross.org/portal'
        self._username = email
        if password == 'use_keyring':
            self._password = 'none' if tokens_file or tokens else \
                             _keyring.get_password(keyring_name, email)
        else:
            self._password = password
        if not self._password:
            raise ValueError('Unable to set password. Please check the email, password, and keyring_name.')
        self._client_id = client_id
        self._key_file = None
        self._cert_file = None
        self._portal = None
        self._con = None
        self._verify_cert = None
        self._datastores_list = None

        existing_tokens = None
        if tokens_file:
            try:
                with open(tokens_file) as f:
                    lines = f.readlines()
                    existing_tokens = {
                        'token': lines[0].strip(),
                        'refresh_token': lines[1].strip()
                    }
            except:
                print('Error using provided tokens, trying user/password authentication.', flush=True)
        elif tokens:
            try:
                existing_tokens = {
                    'token': tokens['RCVIEW_TOKEN'],
                    'refresh_token': tokens['RCVIEW_REFRESH']
                }
            except:
                print('Error using provided tokens, trying user/password authentication.', flush=True)

        self._portal = _RCViewPortal(
            url=self._url, username=self._username,
            password=self._password, client_id=self._client_id,
            spinner=self._spinner,
            existing_tokens=existing_tokens)
        self._con = self._portal.con
        self._tools = _Tools(self)

        _arcgis_env.active_gis = self

        if _print_messages:
            self._spinner.succeed('Login successful')


    def save_tokens(self, file):
        """Save tokens to a file.

        Saves the current RCViewGIS object access tokens to a file so that they
        can be provided to the 'tokens_file' argument.
        """
        with open(file, 'w') as f:
            f.write('{}\n{}\n'.format(self._con._token,
                                      self._con._refresh_token))


class _RCViewPortal(_Portal):
    # A Portal object for RC View.
    def __init__(self, url, username, password, client_id, key_file=None,
                 cert_file=None, expiration=60, referer=None, proxy_host=None,
                 proxy_port=None, connection=None,
                 workdir=_tempfile.gettempdir(), tokenurl=None,
                 verify_cert=True, spinner=None, existing_tokens=None):

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
        self._spinner = spinner

        if _print_messages:
            self._spinner.text = 'Connecting to portal'

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
                                     client_id=client_id,
                                     spinner=self._spinner,
                                     existing_tokens=existing_tokens)
        self.get_properties(True)


class _RCViewConnection(_ArcGISConnection):
    def __init__(self, *args, **kwargs):
        self._spinner = kwargs.pop('spinner')
        self._existing_tokens = kwargs.pop('existing_tokens')
        super().__init__(*args, **kwargs)
    def oauth_authenticate(self, client_id, expiration):
        # Authenticate with RC View single-sign-on.
        if _print_messages:
            self._spinner.text = 'Authenticating user'

        if self._existing_tokens:
            self._refresh_token = self._existing_tokens['refresh_token']
            self._token = self._existing_tokens['token']
            return self._token

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
        options.add_argument("--headless")
        options.add_argument('--log-level=3')
        driver = _webdriver.Chrome(options=options)
        driver.get(codeurl)

        delay = 10
        try:
            using_redcross_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'idp_Name')))
        except _TimeoutException:
            driver.quit()
            if _print_messages:
                self._spinner.fail('Accessing Red Cross single-sign-on took too much time.')

        using_redcross_element.click()

        try:
            username_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[4]/input')))
            password_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[5]/input')))
            signin_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[6]/button')))
        except _TimeoutException:
            driver.quit()
            if _print_messages:
                self._spinner.fail('Accessing Red Cross single-sign-on took too much time.')

        username_element.send_keys(self._username)
        password_element.send_keys(self._password)
        signin_element.click()

        try:
            code_element = _WebDriverWait(driver, delay).\
                until(_EC.presence_of_element_located((_By.ID, 'code')))
        except _TimeoutException:
            driver.quit()
            if _print_messages:
                self._spinner.fail('Receiving an authentication code took too much time.')

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


class RCViewGeocoder(_Geocoder):
    """Subclass of arcgis Geocoder connected to the RC View geocoding service."""
    def __init__(self, gis):
        if not isinstance(gis, RCViewGIS):
            raise TypeError('gis parameter must be an RCViewGIS object.')
        super().__init__('https://maps.rcview.redcross.org/portal/sharing/servers/da9228b803884dda94df19c2f9d83deb/rest/services/World/GeocodeServer', gis)
    def batch_geocode(self, addresses, as_featureset=False, **kwargs):
        """Alternative batch geocoding method which allows specification of additional
        REST API parameters as keyword arguments. See
        https://developers.arcgis.com/rest/geocode/api-reference/geocoding-geocode-addresses.htm
        for details.
        """
        url = self.url + "/geocodeAddresses"
        params = {'f': 'json'}
        for k, v in kwargs.items():
            params[k] = v

        addr_recordset = []

        for index in range(len(addresses)):
            address = addresses[index]

            attributes = {"OBJECTID": index}
            if isinstance(address, str):
                attributes[self._address_field] = address
            elif isinstance(address, dict):
                attributes.update(address)
            else:
                print("Unsupported address: " + str(address))
                print("address should be a string (single line address) or dictionary "
                      "(with address fields as keys)")

            addr_rec = {"attributes": attributes}
            addr_recordset.append(addr_rec)

        params['addresses'] = {"records": addr_recordset}

        resp = self._con.post(url, params, token=self._token)
        if resp is not None and as_featureset:
            sr = resp['spatialReference']

            matches = [None] * len(addresses)
            locations = resp['locations']
            for location in locations:
                geom = _copy.copy(location['location'])
                if 'spatialReference' not in geom:
                    geom['spatialReference'] = sr
                att = location['attributes']
                matches[location['attributes']['ResultID']] = {'geometry': _Geometry(geom),
                                                               "attributes" : att }
            return _FeatureSet(features=matches, spatial_reference=sr)
        elif resp is not None and as_featureset == False:
            matches = [None] * len(addresses)
            locations = resp['locations']
            for location in locations:
                matches[location['attributes']['ResultID']] = location
            return matches
        else:
            return []
