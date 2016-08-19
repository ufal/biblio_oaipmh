# coding=utf-8
# https://guidelines.openaire.eu/en/latest/literature/use_of_oai_pmh.html

import os
import logging
import xml.etree.ElementTree

_logger = logging.getLogger()


class base_biblio(object):
    def __init__(self, f, ftor=None):
        self.f = f
        self.ids = {}
        self._parse(ftor)

    def _parse(self, ftor):
        root = xml.etree.ElementTree.parse( self.f ).getroot()
        for elem in root.findall( 'Record' ):
            if ftor is None:
                self.ids[elem.get('Id')] = {}
            else:
                v = ftor(elem)
                if v is not None:
                    self.ids[elem.get( 'Id' )] = v
        _logger.info("Found [%d] entries in [%s]", len(self.ids), self.f)


class authors(base_biblio):
    def __init__(self, f):
        def format_names(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            #last, first for now check with https://guidelines.openaire.eu/en/latest/literature/field_creator.html#dc-creator
            first = d.get('First name')
            last = d.get('Last name')
            if first == last == None:
                _logger.error("No names for %s", elem.get('Id'))
                return None
            ret = ""
            if last is not None:
                ret += last
                if first is not None:
                    ret += ", "
            if first is not None:
                ret += first
            return ret
        super( authors, self ).__init__( f, format_names )


class grants(base_biblio):
    supported = ("EU", )

    def __init__(self, f):
        def filter_ids(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            return d if d.get("Agency", "") in grants.supported \
                else None
        super( grants, self ).__init__( f, filter_ids )


class publications(base_biblio):
    def __init__(self, f, grants):
        ids = set(grants.ids.keys())

        def filter_ids(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            supported = d.get("Supported by", "") or ""
            auths = d.get("Author(s)", "") or ""
            d["Supported by"] = set(supported.split(";"))
            d["Author(s)"] = set(auths.split(";"))
            return d if 0 < len(d["Supported by"] & ids) else None
        super( publications, self ).__init__( f, filter_ids )


class biblio(object):

    dc_template = u"""
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:dc="http://purl.org/dc/elements/1.1/" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
%s
</oai_dc:dc>
"""

    def __init__(self, d):
        self.authors = authors(os.path.join(d, "authors.xml"))
        self.grants = grants( os.path.join( d, "grants.xml" ) )
        self.publications = publications( os.path.join( d, "publications.xml" ), self.grants )
        self.identifiers = self.publications.ids

    def to_dc(self, identifier):
        rec = self.publications.ids[identifier]
        #Mandatory fields
        dc_title = '\n'.join([u"<dc:title>%s</dc:title>" % rec[title_field] if rec[title_field] is not None else ""
                              for title_field in ["Title", "Original title", "English title", "Czech title"]])
        dc_creators = ""
        try:
            dc_creators = u"\n".join([ u"<dc:creator>%s</dc:creator>" % self.authors.ids[author_id] for author_id in rec.get("Author(s)")])
        except KeyError:
            _logger.error("Error fetching authors for %s", identifier)
#        # Project identifier info:eu-repo/grantAgreement
#        dc_relation =
#        #Access level info:eu-repo/semantics
#        dc_rights
#        #XXX: subject/keywords nothing to map?
#        #dc_subject
#        #EnglishAbstract
#        dc_description
#        #Publisher
#        dc_publisher
#        #publication date
#        #Use Year for now, there is also a date field
#        dc_date
#        #publication type info:eu-repo/semantics/
#        dc_type
#        #XXX: resource identifier, (URL,DOI,URN:NBN,ISBN,ISSN,etc.), do we put there biblio URL, if URL is empty?
#        dc_identifier
        dc_metadata = dc_title + '\n' + dc_creators
        return biblio.dc_template % dc_metadata


class Provider(object):
    """
    Metadata provider for DDI Codebook XML files.
    """

    def __init__(self, domain_name='biblio.ufal.mff.cuni.cz', directory='./input'):
        """
        Initialize the metadata provider.

        Parameters
        ----------
        directory: str
            Path of the directory to scan for DDI files.
        domain_name: str
            The domain name part of the OAI identifiers.
        """
        self.oai_identifier_prefix = 'oai:{0}:'.format(domain_name)
        self.directory = directory

    def formats(self):
        """
        List the available metadata formats.

        Return
        ------
        dict from unicode to (unicode, unicode):
            Mapping from metadata prefixes to (namespace, schema location)
            tuples.
        """
        # Only OAI DC is available from this provider.
        return {
            'oai_dc': ('http://www.openarchives.org/OAI/2.0/oai_dc/',
                       'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'),
        }

    def identifiers(self):
        """
        List all identifiers.

        Return
        ------
        iterable of str:
            OAI identifiers of all items
        """
        logging.debug('Parsing directory {0} for biblio related files...', self.directory)

        #
        self.biblio = biblio(self.directory)

        for identifier in self.biblio.identifiers:
            yield self.make_identifier(identifier)

    def has_changed(self, identifier, since):
        """
        Check wheter the given item has been modified.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.
        since: datetime.datetime
            Ignore modifications before this date/time.

        Return
        ------
        bool:
            `True`, if metadata or sets of the item have change since the
            given time. Otherwise `False`.
        """
        return True

    def get_sets(self, identifier):
        """
        List sets of an item.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.

        Return
        ------
        iterable of (unicode, unicode):
            (set spec, set name) pairs for all sets which contain the given
            item. In case of hierarchical sets, return all sets in the
            hierarchy (e.g. if the result contains the set `a:b:c`, sets
            `a:b` and `a` must also be included).
        """
        # This provider does not use sets.
        return [ ("openaire", "openaire") ]

    def get_record(self, identifier, metadata_prefix):
        """
        Fetch the metadata of an item.

        Parameters
        ----------
        identifier: unicode
            The OAI identifier (as returned by identifiers()) of the item.
        metadata_prefix: unicode
            The metadata prefix (as returned by formats()) of the format.

        Return
        ------
        str or NoneType:
            An XML fragment containing the metadata of the item in the
            given format. If the format is not available for the item
            return `None`.

        Raises
        ------
        Exception:
            If converting or reading the metadata fails.
        """
        if metadata_prefix != 'oai_dc':
            return None

        return self.biblio.to_dc(identifier[len(self.oai_identifier_prefix):])

    def make_identifier(self, identifier):
        """
        Form an OAI identifier for the given file.
        """
        return self.oai_identifier_prefix + identifier
