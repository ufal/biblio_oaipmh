# coding=utf-8
# https://guidelines.openaire.eu/en/latest/literature/use_of_oai_pmh.html

import os
import logging
import xml.etree.ElementTree
from xml.sax.saxutils import escape

_logger = logging.getLogger()


class base_biblio(object):
    def __init__(self, f, ftor=None):
        self.f = f
        self.ids = {}
        self._parse(ftor)

    def _parse(self, ftor):
        root = xml.etree.ElementTree.parse(self.f).getroot()
        for elem in root.findall('Record'):
            if ftor is None:
                self.ids[elem.get('Id')] = {}
            else:
                v = ftor(elem)
                if v is not None:
                    self.ids[elem.get('Id')] = v
        _logger.info("Found [%d] entries in [%s]", len(self.ids), self.f)


class authors(base_biblio):
    def __init__(self, f):
        def format_names(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            #XXX: last, first for now check with https://guidelines.openaire.eu/en/latest/literature/field_creator.html#dc-creator
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

        super(authors, self).__init__(f, format_names)


class grants(base_biblio):
    supported = ("EU",)

    def __init__(self, f, openaire):
        def filter_ids(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            if d.get("Agency", "") in grants.supported:
                code = d.get("Code")
                d["openaire_id"] = self._get_openaire_id(code, openaire)
                return d

            return None

        super(grants, self).__init__(f, filter_ids)

    def _get_openaire_id(self, code, openaire):
        if code is None:
            return None
        ids = code.split('-')
        if ids[-1].isdigit():
            id = ids[-1]
        elif len(ids) > 1 and ids[-2].isdigit():
            id = ids[-2]
        else:
            id = None
        if id is None:
            _logger.error("Failed to parse grant code %s", code)
            return None
        results = [];
        for openaire_id in openaire.ids.keys():
            if id in openaire_id:
                results.append(openaire_id)

        if len(results) == 1:
            return results[0]
        else:
            _logger.error("Failed to uniquely identify openaire project from code %s", code)
            return None

class publications(base_biblio):
    def __init__(self, f, grants):
        grant_ids = set(grants.ids.keys())

        def filter_ids(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            supported = d.get("Supported by", "") or ""
            auths = d.get("Author(s)", "") or ""
            d["Supported by"] = set(supported.split(";")) & grant_ids
            d["Author(s)"] = set(auths.split(";"))
            return d if 0 < len(d["Supported by"]) else None

        super(publications, self).__init__(f, filter_ids)


class Openaire(object):
    def __init__(self, f):
        self.f = f
        self.ids = {}
        self._parse()

    def _parse(self):
        root = xml.etree.ElementTree.parse(self.f).getroot()
        for elem in root.findall('.//pair'):
            id = elem.find("stored-value").text
            self.ids[id] = {}
        _logger.info("Found [%d] entries in [%s]", len(self.ids), self.f)


class biblio(object):
    dc_template = u"""
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:dc="http://purl.org/dc/elements/1.1/" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
%s
</oai_dc:dc>
"""

    def __init__(self, d):
        # List of openaire projects as used and fetched by dspace. [dspace]/config/openaire-cache.list
        self.openaire = Openaire(os.path.join(d, "openaire-cache.list"))
        self.authors = authors(os.path.join(d, "authors.xml"))
        self.grants = grants(os.path.join(d, "grants.xml"), self.openaire)
        self.publications = publications(os.path.join(d, "publications.xml"), self.grants)
        self.identifiers = self.publications.ids

    def to_dc(self, identifier):
        rec = self.publications.ids[identifier]
        # Mandatory fields
        dc_title = '\n'.join([u"<dc:title>%s</dc:title>" % escape(rec[title_field]) if rec[title_field] is not None else ""
                              for title_field in ["Title", "Original title", "English title", "Czech title"]])
        dc_creators = ""
        try:
            dc_creators = u"\n".join([u"<dc:creator>%s</dc:creator>" % escape(self.authors.ids[author_id])
                                      for author_id in rec.get("Author(s)")])
        except KeyError:
            _logger.error("Error fetching authors for %s", identifier)
        # Project identifier info:eu-repo/grantAgreement
        dc_relations = ''
        try:
            dc_relations = u"\n".join([u"<dc:relation>%s</dc:relation>" % self.grants.ids[grant_id]["openaire_id"]
                                      for grant_id in rec.get("Supported by")])
        except KeyError:
            _logger.error("Error fetching openaire_id for %s", identifier)
        #Access level info:eu-repo/semantics
        #XXX: hardcoded openaccess
        dc_rights = u"<dc:rights>%s</dc:rights>" % 'info:eu-repo/semantics/openAccess'
        #XXX: subject/keywords nothing to map?
        #        #dc_subject
        #description...use english abstract
        dc_description = u"<dc:description>%s</dc:description>" % escape(rec.get("English abstract")) if rec.get("English abstract") is not None else ""
        #Publisher
        dc_publisher = u"<dc:publisher>%s</dc:publisher>" % escape(rec.get("Publisher")) if rec.get("Publisher") is not None else ""
        #publication date #Use Year for now, there is also a date field
        dc_date = u"<dc:date>%s</dc:date>" % rec.get("Year") if rec.get("Year") is not None else ""
        #publication type info:eu-repo/semantics/
        #XXX come up with a mapping from
        # 630 Inproceedings
        # 460 InProceedingsWithoutISBN
        # 274 OralPresentation
        # 241 Article
        # 192 DataSW
        # 83 Inbook
        # 62 Techreport
        # 48 PosterAbstractDemo
        # 34 Book
        # 31 Phdthesis
        # 24 Review
        # 18 Prototype
        # 16 Mastersthesis
        # 15 Popular
        # 4 Electronic
        # 2 LectureNotes
        # 2 Habilitation
        # 1 Survey
        # 1 Proceedings
        # 1 ArticleTranslation
        #        TO
        #        info:eu - repo / semantics / article
        #        info:eu - repo / semantics / bachelorThesis
        #        info:eu - repo / semantics / masterThesis
        #        info:eu - repo / semantics / doctoralThesis
        #        info:eu - repo / semantics / book
        #        info:eu - repo / semantics / bookPart
        #        info:eu - repo / semantics / review
        #        info:eu - repo / semantics / conferenceObject
        #        info:eu - repo / semantics / lecture
        #        info:eu - repo / semantics / workingPaper
        #        info:eu - repo / semantics / preprint
        #        info:eu - repo / semantics / report
        #        info:eu - repo / semantics / annotation
        #        info:eu - repo / semantics / contributionToPeriodical
        #        info:eu - repo / semantics / patent
        #        info:eu - repo / semantics / other
        #        dc_type
        #XXX: resource identifier, (URL,DOI,URN:NBN,ISBN,ISSN,etc.), do we put there biblio URL, if URL is empty, can we get more details for InProceedings?
        #        dc_identifier
        #XXX Make sure the values in those fields are properly escaped!
        dc_metadata = '\n'.join([dc_title, dc_creators, dc_relations, dc_rights, dc_description, dc_publisher, dc_date])
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
        return [("openaire", "openaire")]

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
