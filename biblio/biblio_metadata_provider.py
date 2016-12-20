# coding=utf-8
# https://guidelines.openaire.eu/en/latest/literature/use_of_oai_pmh.html

import os
import logging
import xml.etree.ElementTree
import requests
import json
logging.getLogger("requests").setLevel(logging.WARNING)
from xml.sax.saxutils import escape
from collections import defaultdict

_logger = logging.getLogger()


class base_biblio(object):

    def __init__(self, f, ftor=None):
        self.f = f
        self.ids = {}
        self._parse(ftor)

    def _parse(self, ftor):
        root = xml.etree.ElementTree.parse(self.f).getroot()
        for pos, elem in enumerate(root.findall('Record')):
            if ftor is None:
                self.ids[elem.get('Id')] = {}
            else:
                v = ftor(elem)
                if v is not None:
                    # we want to use different ids e.g., in attachments
                    id_str = elem.get('Id') if not isinstance(v, dict) \
                        else v.get("id", elem.get('Id'))
                    self.ids[id_str] = v
        _logger.info("Found [%d] entries in [%s]", len(self.ids), self.f)


class authors(base_biblio):

    def __init__(self, f):
        def format_names(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            # XXX: last, first for now check with
            # https://guidelines.openaire.eu/en/latest/literature/field_creator.html#dc-creator
            first = d.get('First name')
            last = d.get('Last name')
            if first == last and last is None:
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
    unsupported_prefixex = ("FP6", )

    def __init__(self, f, openaire):
        def filter_ids(elem):
            d = dict((x.get("Label"), x.text) for x in elem)
            if d.get("Agency", "") in grants.supported:
                code = d.get("Code")
                for up in grants.unsupported_prefixex:
                    if code.startswith(up):
                        return None
                openaire_code = grants._get_openaire_id(code, openaire)
                if openaire_code is not None:
                    d["openaire_id"] = grants._get_openaire_id(code, openaire)
                    return d
            return None

        super(grants, self).__init__(f, filter_ids)

    @staticmethod
    def _get_openaire_id(code, openaire):
        code = code.strip()
        if code is None:
            return None
        ids = code.split('-')
        if ids[-1].isdigit():
            id_str = ids[-1]
        elif len(ids) > 1 and ids[-2].isdigit():
            id_str = ids[-2]
        else:
            _logger.error("Failed to parse grant code %s", code)
            return None
        results = []
        for openaire_id in openaire.ids.keys():
            if id_str in openaire_id:
                results.append(openaire_id)

        if len(results) == 1:
            return results[0]
        else:
            _logger.error(
                "Failed to uniquely identify openaire project from code %s", code)
            return None


class attachments(base_biblio):

    def __init__(self, f):
        def filter_ids(elem):
            d = dict((x.get("Name"), x.text) for x in elem)
            # publication id is in Parent
            d["id"] = elem.get('Parent')
            return d
        super(attachments, self).__init__(f, filter_ids)


class publications(base_biblio):
    cannot_handle_yet = [
        "7422113138842492486"
    ]

    __dbg_look_for = [
        #"-256585522970273362"
    ]

    def __init__(self, f, grants_inst):
        grant_ids = set(grants_inst.ids.keys())

        def filter_ids(elem):
            if elem.get('Id') in publications.cannot_handle_yet:
                return None
            if 0 < len(publications.__dbg_look_for):
                if elem.get('Id') not in publications.__dbg_look_for:
                    return None
            d = dict((x.get("Label"), x.text) for x in elem)
            supported = d.get("Supported by", "") or ""
            d["Supported by"] = set(supported.split(";")) & grant_ids
            authorz = d.get("Author(s)", "") or ""
            d["Author(s)"] = set(authorz.split(";"))
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
            id_str = elem.find("stored-value").text
            self.ids[id_str] = {}
        _logger.info("Found [%d] entries in [%s]", len(self.ids), self.f)


class biblio(object):
    dc_template = u"""
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:dc="http://purl.org/dc/elements/1.1/" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
%s
</oai_dc:dc>
"""

    # https://guidelines.openaire.eu/en/latest/literature/field_publicationtype.html
    type_mapping = {
        "Article": "info:eu-repo/semantics/article",

        "Inproceedings": "info:eu-repo/semantics/conferenceObject",
        "InProceedingsWithoutISBN": "info:eu-repo/semantics/conferenceObject",
        "PosterAbstractDemo": "info:eu-repo/semantics/conferenceObject",
        "OralPresentation": "info:eu-repo/semantics/conferenceObject",

        "Mastersthesis": "info:eu-repo/semantics/masterThesis",
        "Phdthesis": "info:eu-repo/semantics/doctoralThesis",

        "Book": "info:eu-repo/semantics/book",
        "Inbook": "info:eu-repo/semantics/bookPart",

        "Techreport": "info:eu-repo/semantics/report",

        "DataSW": "info:eu-repo/semantics/other",
    }

    access_map_file = "accesses.json"

    def __init__(self, d):
        # List of openaire projects as used and fetched by dspace.
        # [dspace]/config/openaire-cache.list
        self.attachments = attachments(os.path.join(d, "attachedfiles.xml"))
        self.openaire = Openaire(os.path.join(
            "input_openaire", "openaire-cache.list"))
        self.authors = authors(os.path.join(d, "authors.xml"))
        self.grants = grants(os.path.join(d, "grants.xml"), self.openaire)
        self.publications = publications(
            os.path.join(d, "publications.xml"), self.grants
        )
        self.identifiers = self.publications.ids
        self._cnts = defaultdict(int)
        self._access_map = json.load(open(biblio.access_map_file, mode="r")) \
            if os.path.exists(biblio.access_map_file) else {}

    def __del__(self):
        print self._cnts
        if 0 < len(self._access_map):
            json.dump(
                self._access_map,
                open(biblio.access_map_file, mode="w+"),
                indent=2, sort_keys=True
            )

    @staticmethod
    def _fill_values(metadata_key, ftor_get, record_keys, subst_dict, value_mapper=None):
        values = [ftor_get(k).strip()
                  for k in record_keys if ftor_get(k) is not None]
        if value_mapper is not None:
            values = [value_mapper(x) for x in values]
        subst_values = [subst_dict[metadata_key] % escape(x) for x in values]
        subst_dict[metadata_key] = u'\n'.join(
            [x for x in subst_values if 0 < len(x)]).strip()
        return values

    def to_dc(self, identifier):
        record_template = u"""
{ids}
{title}
{creators}
{relations}
{rights}
{descriptions}
{publishers}
{dates}
{type}
"""

        # will be substituted afterwards
        vals = {
            "ids": u"<dc:identifier>%s</dc:identifier>",
            "title": u"<dc:title>%s</dc:title>",
            "creators": u"<dc:creator>%s</dc:creator>",
            "relations": u"<dc:relation>%s</dc:relation>",
            "rights": u"<dc:rights>%s</dc:rights>",
            "descriptions": u"<dc:description>%s</dc:description>",
            "publishers": u"<dc:publisher>%s</dc:publisher>",
            "dates": u"<dc:date>%s</dc:date>",
            "type":  u"<dc:type>%s</dc:type>",
        }

        rec = self.publications.ids[identifier]

        # Mandatory fields
        try:
            vals["ids"] %= "http://hdl.handle.net/11346/BIBLIO@id=" + identifier

            # get first title
            for key_title in ["Title", "Original title", "English title", "Czech title"]:
                val = self._fill_values("title", rec.get, [key_title], vals)
                if 0 < len(val):
                    break

            self._fill_values(
                "creators", self.authors.ids.get, rec.get("Author(s)"), vals
            )
            # Project identifier info:eu-repo/grantAgreement
            self._fill_values(
                "relations",
                lambda k: self.grants.ids[k]["openaire_id"],
                rec.get("Supported by"),
                vals
            )

            # Access level info:eu-repo/semantics
            # XXX: hardcoded openaccess
            access = self._find_access(rec, identifier)
            vals["rights"] %= access
            self._cnts[access] += 1

            # XXX: subject/keywords nothing to map?
            #        #dc_subject
            # description...use english abstract
            self._fill_values(
                "descriptions", rec.get, ["English abstract"], vals
            )

            # Publisher
            self._fill_values("publishers", rec.get, ["Publisher"], vals)

            # publication date #Use Year for now, there is also a date field
            self._fill_values("dates", rec.get, ["Year"], vals)

            #
            self._fill_values(
                "type", rec.get, ["Type"], vals, biblio.map_to_type
            )

        except KeyError, e:
            _logger.error(
                "Error fetching mandatory metadata for %s [%s]", identifier, repr(e))
            return None

        return biblio.dc_template % record_template.strip().format(**vals)

    def _find_access(self, rec, id_str):
        open_access = "info:eu-repo/semantics/openAccess"
        closed_access = "info:eu-repo/semantics/closedAccess"

        # already done?
        if id_str in self._access_map:
            return self._access_map[id_str]

        access = None

        # based on attachment
        attach = self.attachments.ids.get(id_str, {})
        if "pdf" in attach.get("FileCType", ""):
            if "public" == attach.get("Access", ""):
                access = open_access

        # based on URL
        if access is None:
            urls = rec.get("URL")
            access = closed_access
            if urls is not None and 0 < len(urls):
                self._cnts["urls"] += 1
                if not ("[" == urls[0] and "]" == urls[-1]):
                    _logger.warn("Invalid url: %s", urls)
                    urls = []
                if "], [" in urls:
                    _logger.warn("Multiple urls: %s", urls)
                    # todo: use regexp
                    urls = [x.lstrip("[").rstrip("]")
                            for x in urls.split("], [")]
                else:
                    urls = [urls[1:-1]]

                for url in urls:
                    if access != closed_access:
                        break
                    is_magic = False
                    for magic in (
                            "github.com",
                            "hdl.handle.net/",
                            "http://www.lrec-conf.org/",
                            "http://ufal.mff.cuni.cz/",
                    ):
                        if magic in url:
                            access = open_access
                            is_magic = True
                            break

                    status = -1
                    if not is_magic:
                        try:
                            r = requests.head(url)
                            status = r.status_code
                            if status == 200:
                                if "/pdf" in r.headers['content-type']:
                                    access = open_access
                        except requests.ConnectionError, e:
                            _logger.warn("Url [%s] problem [%s]", url, repr(e))

                    print "%3d. URL: [%3s] [%15s] %s" % (
                        self._cnts["urls"], status, access[-15:], url
                    )

        # store info
        self._access_map[id_str] = access
        return access

    @staticmethod
    def map_to_type(tp):
        # 274 OralPresentation
        # 241 Article
        # 192 DataSW
        # 83 Inbook
        # 62 Techreport
        # 48 PosterAbstractDemo
        # 34 Book
        # 24 Review
        # 18 Prototype
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
        # XXX: resource identifier, (URL,DOI,URN:NBN,ISBN,ISSN,etc.), do we put there biblio URL, if URL is empty, can we get more details for InProceedings?
        #        dc_identifier
        # XXX Make sure the values in those fields are properly escaped!
        if tp not in biblio.type_mapping:
            _logger.warn("Type mapping not found for [%s]", tp)
        return biblio.type_mapping.get(tp, "info:eu-repo/semantics/other")


class Provider(object):
    """
    Metadata provider for DDI Codebook XML files.
    """

    def __init__(self, domain_name='biblio.ufal.mff.cuni.cz', directory='./input_biblio'):
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
        logging.debug(
            'Parsing directory {0} for biblio related files...', self.directory)

        #
        self.biblio = biblio(self.directory)

        for identifier in self.biblio.identifiers:
            yield self.make_identifier(identifier)

    def has_changed(self, identifier, since):
        """
            Check whether the given item has been modified.

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
