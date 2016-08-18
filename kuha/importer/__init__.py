import errno
import importlib
import logging
import os
import sys

from pyramid.paster import get_appsettings, setup_logging
from pyramid.scripts.common import parse_vars

from ..exception import HarvestError
from ..config import clean_importer_settings
from ..models import create_engine, ensure_oai_dc_exists
from ..util import (
    datestamp_now,
    parse_date,
    format_datestamp,
)
from ..importer.harvest import update

def usage(argv):
    usage_string = '''Usage: {0} <config_uri> [var=value]...
Update the Kuha database.

See the sample configuration file for details.'''
    cmd = os.path.basename(argv[0])
    print(usage_string.format(cmd))
    sys.exit(1)


def read_timestamp(path):
    log = logging.getLogger(__name__)

    if not path:
        log.warning('Timestamp file has not been configured.')
        return None

    try:
        with open(path, 'r') as file_:
            (time, _) = parse_date(file_.read())
        return time
    except ValueError as error:
        log.error('Invalid timestamp file "{0}"'.format(path))
    except IOError as error:
        if error.errno == errno.ENOENT:
            log.info('Timestamp file does not exist.')
        else:
            log.error(
                'Failed to read timestamp file "{0}": {1}'
                ''.format(path, error)
            )
    return None


def write_timestamp(path, time):
    log = logging.getLogger(__name__)

    if not path:
        return

    text = format_datestamp(time)
    try:
        with open(path, 'w') as file_:
            file_.write(text)
    except IOError as error:
        log.error(
            'Failed to record timestamp to "{0}": {1}'
            ''.format(path, error)
        )


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])

    settings = get_appsettings(config_uri, options=options)
    clean_importer_settings(settings)

    setup_logging(settings['logging_config'])
    log = logging.getLogger(__name__)

    purge = settings['deleted_records'] == 'no'
    dry_run = settings['dry_run']

    if dry_run:
        log.info('Starting metadata import (dry run)...')
    else:
        log.info('Starting metadata import...')

    timestamp_file = settings['timestamp_file']
    old_timestamp = (None if settings['force_update'] else
                     read_timestamp(timestamp_file))

    # Get timestamp before harvest.
    new_timestamp = datestamp_now()

    create_engine(settings)
    if not dry_run:
        ensure_oai_dc_exists()

    log.debug('Loading the metadata provider...')
    try:
        modulename, classname = settings['metadata_provider_class']
        log.debug('Using class "{0}" from module "{1}"'
                  ''.format(classname, modulename))
        provider_module = importlib.import_module(modulename)
        Provider = getattr(provider_module, classname)
        args = settings['metadata_provider_args'].split()
        metadata_provider = Provider(*args)
    except Exception as error:
        log.critical(
            'Failed to initialize the metadata provider: {0}'
            ''.format(error),
            exc_info=True,
        )
        raise

    log.debug('Harvesting metadata...')
    try:
        update(metadata_provider, old_timestamp, purge, dry_run)
    except HarvestError as error:
        log.critical(
            'Failed to harvest metadata: {0}'
            ''.format(error)
        )
        raise

    if not dry_run:
        write_timestamp(timestamp_file, new_timestamp)

    log.info('Done.')
