"""Module contains Flask config for production and dev environment.
"""

# NOTE: update server/lib/config.py when adding/removing config.

import os


class Config:
    TEST = False
    WEBDRIVER = False
    LOCAL = False
    LITE = False
    VERSION = '{}-{}'.format(os.environ.get('WEBSITE_HASH'),
                             os.environ.get('MIXER_HASH'))
    API_ROOT = 'http://127.0.0.1:8081'  # Port for Kubernetes ESP.
    RECON_API_ROOT = 'http://127.0.0.1:8081'
    SECRET_PROJECT = os.environ.get('SECRET_PROJECT') or ''
    MAPS_API_KEY = os.environ.get('MAPS_API_KEY') or ''
    GA_ACCOUNT = ''
    SCHEME = 'https'
    # Additional stat vars that need to be fetched for place page data.
    # This is only needed for local development when cache is not up to date.
    NEW_STAT_VARS = []
    ENABLE_BLOCKLIST = False
    # If the deployment is a private instance.
    PRIVATE = False
    # If the deployment is for "feeding america" instance.
    FEEDING_AMERICA = False
    # If the deployment is for sustainability.datacommons.org.
    SUSTAINABILITY = False
    # Name of the site. The name is changed for private instance.
    NAME = "Data Commons"


class ProductionConfig(Config):
    GA_ACCOUNT = 'UA-117119267-1'
    ENABLE_BLOCKLIST = True


class ProdSustainabilityConfig(ProductionConfig):
    SUSTAINABILITY = True


class StagingConfig(Config):
    ENABLE_BLOCKLIST = True
    pass


class StagingSustainabilityConfig(StagingConfig):
    SUSTAINABILITY = True


class AutopushConfig(Config):
    pass


class AutopushSustainabilityConfig(AutopushConfig):
    SUSTAINABILITY = True


class DevConfig(Config):
    pass


class PrivateConfig(Config):
    PRIVATE = True


class FeedingAmericaConfig(PrivateConfig):
    NAME = "Feeding America"
    FEEDING_AMERICA = True


class TidalConfig(PrivateConfig):
    NAME = "Tidal"


######
#
# All the config below runs as non-GKE deployment, hence needs to set fields
# like  `SECRET_PROJECT`
#
#####


class MinikubeConfig(Config):
    LOCAL = True
    SCHEME = 'http'


class LocalConfig(Config):
    LOCAL = True
    SECRET_PROJECT = 'datcom-website-dev'
    API_ROOT = 'https://autopush.api.datacommons.org'
    RECON_API_ROOT = 'https://autopush.recon.datacommons.org'
    SCHEME = 'http'


class LocalSustainabilityConfig(LocalConfig):
    SUSTAINABILITY = True


class LocalPrivateConfig(PrivateConfig):
    # This needs to talk to local mixer that is setup as a private mixer, which
    # loads csv + tmcf files from GCS
    API_ROOT = 'https://mixer.endpoints.datcom-mixer-statvar.cloud.goog'
    RECON_API_ROOT = 'https://autopush.recon.datacommons.org'
    LOCAL = True
    SECRET_PROJECT = 'datcom-website-private'
    NAME = "Feeding America"
    SCHEME = 'http'


class LocalLiteConfig(Config):
    LOCAL = True
    LITE = True
    API_ROOT = 'https://autopush.api.datacommons.org'
    RECON_API_ROOT = 'https://autopush.recon.datacommons.org'
    SCHEME = 'http'


class WebdriverConfig(Config):
    WEBDRIVER = True
    SECRET_PROJECT = 'datcom-website-dev'
    API_ROOT = 'https://autopush.api.datacommons.org'
    RECON_API_ROOT = 'https://autopush.recon.datacommons.org'
    SCHEME = 'http'


class TestConfig(Config):
    TEST = True
    API_ROOT = 'api-root'
    SCHEME = 'http'


class TestSustainabilityConfig(TestConfig):
    SUSTAINABILITY = True
