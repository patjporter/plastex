"""
Package thmextras
Goodies for theorem environment and sample specific plasTeX package.
"""
import os
import string
from jinja2 import Template

from plasTeX import Command
from plasTeX.Base.LaTeX.Lists import List
from plasTeX.PackageResource import (
        PackageTemplateDir, PackageJs, PackageCss, PackageResource)

from plasTeX.Logging import getLogger
log = getLogger()


class uses(Command):
    """ \uses{labels list} """
    args = 'labels:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_used():
            labels_dict = doc.context.labels
            used = [labels_dict[label] for label in self.attributes['labels'] if label in labels_dict]
            node.setUserData('uses', used)
            if 'thmextras_dep_graph' in doc.userdata:
                graph = doc.userdata.get('thmextras_dep_graph')
                graph.add_node(node)
                graph.add_nodes_from(used)
                for thm in used:
                    graph.add_edge(thm, node)

        doc.postParseCallbacks.append(update_used)

class proves(Command):
    """ \proves{label} """
    args = 'label:str'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_proved():
            labels_dict = doc.context.labels
            proved = labels_dict.get(self.attributes['label'])
            if proved:
                node.setUserData('proves', proved)
                proved.userdata['proved_by'] = node
        doc.postParseCallbacks.append(update_proved)


class quizz(List):
    class qwrong(List.item):
        pass

    class qright(List.item):
        pass

    class question(Command):
        args = 'self'

        def digest(self, tokens):
            Command.digest(self, tokens)
            node = self.parentNode
            node.userdata['question'] = self

    def digest(self, tokens):
        List.digest(self, tokens)
        node = self.parentNode
        quizzes = node.userdata.get('quizzes', [])
        quizzes.append(self)
        node.userdata['quizzes'] = quizzes


class covers(Command):
    """ \covers{labels list} """
    args = 'labels:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_covered():
            labels_dict = doc.context.labels
            covereds = [labels_dict[label] 
                    for label in self.attributes['labels'] 
                    if label in labels_dict]
            node.setUserData('covers', covereds)
            for covered in covereds:
                covered_by = covered.userdata.get('covered_by', [])
                covered.setUserData('covered_by', covered_by + [node])
        doc.postParseCallbacks.append(update_covered)


class ThmReport():
    """"""

    def __init__(self, id, caption, statement, covered_by):
        """Constructor for ThmReport"""
        self.id = id
        self.caption = caption
        self.statement = statement
        self.covered_by = covered_by

    @classmethod
    def from_thm(cls, thm):
        covered_by = thm.userdata.get('covered_by', [])
        caption = thm.caption + ' ' + thm.ref
        return cls(thm.id, caption, unicode(thm), covered_by)


class PartialReport():
    def __init__(self, title, nb_thms, nb_not_covered, thm_reports):
        self.nb_thms = nb_thms
        self.nb_not_covered = nb_not_covered
        self.coverage = 100 * (nb_thms - nb_not_covered) / nb_thms if nb_thms else 100
        self.thm_reports = thm_reports
        self.title = title
        if self.coverage == 100:
            self.status = 'ok'
        elif self.coverage > 0:
            self.status = 'partial'
        else:
            self.status = 'void'

    @classmethod
    def from_section(cls, section, thm_types):
        nb_thms = 0
        nb_not_covered = 0
        thm_reports = []
        theorems = []
        for thm_type in thm_types:
            theorems += section.getElementsByTagName(thm_type)
        for thm in theorems:
            nb_thms += 1
            thm_report = ThmReport.from_thm(thm)
            if not thm_report.covered_by:
                nb_not_covered += 1
            thm_reports.append(thm_report)
        return cls(section.fullTocEntry, nb_thms, nb_not_covered, thm_reports)


class Report():
    """A full report."""

    def __init__(self, partials):
        """Constructor for Report"""
        self.partials = partials
        self.nb_thms = sum([p.nb_thms for p in partials])
        self.nb_not_covered = sum([p.nb_not_covered for p in partials])
        self.coverage = 100 * (self.nb_thms - self.nb_not_covered) / self.nb_thms if self.nb_thms else 100



def ProcessOptions(options, document):
    """This is called when the package is loaded."""

    templatedir = PackageTemplateDir(
            renderers=['html5'],
            package='thmextras')

    document.addPackageResource(templatedir)

    jobname = document.userdata['jobname']
    outdir = document.config['files']['directory']
    outdir = string.Template(outdir).substitute({'jobname': jobname})

    links = PackageResource(
            renderers=['html5'],
            key='thmextras_usage_links',
            data='usage_links' in options)
    document.addPackageResource(links)

    if 'dep_graph' in options:
        ok = True
        try:
            import networkx as nx
        except ImportError:
            log.warning('Dependency graphs need networkx package.')
            ok = False
        try:
            import numpy
        except ImportError:
            log.warning('Dependency graphs need numpy package.')
            ok = False
        if ok:
            document.userdata['thmextras_dep_graph'] = nx.DiGraph()
            graph_target = options.get( 'dep_graph_target', 'dep_graph.html')
            
            default_template = os.path.join(os.path.dirname(__file__), 'dep_graph.j2')
            graph_template = options.get( 'dep_graph_tpl', default_template)
            try: 
                with open(graph_template) as src:
                    tpl = Template(src.read())
            except IOError:
                log.warning('DepGraph template read error, using default template')
                with open(default_template) as src:
                    tpl = Template(src.read())

            def makeDepGraph(document):
                graph = document.userdata['thmextras_dep_graph']
                positions = nx.spring_layout(graph, iterations=100)
                tpl.stream(
                        graph=graph,
                        positions=positions,
                        context=document.context,
                        config=document.config).dump(graph_target)
                return [graph_target]

            cb = PackageResource(
                    renderers=['html5'],
                    key='preCleanupCallbacks',
                    data=makeDepGraph)
            css = PackageCss(
                    renderers=['html5'],
                    package='thmextras',
                    data='dep_graph.css')
            js = PackageJs(
                    renderers=['html5'],
                    package='thmextras',
                    data='dep_graph.js')
            sigmajs = PackageJs(
                    renderers=['html5'],
                    package='thmextras',
                    data='sigma.min.js')
            document.addPackageResource([cb, css, js, sigmajs])

    if 'quizz' in options:
        js = PackageJs(
                renderers=['html5'],
                package='thmextras',
                data='quizz.js')
        document.addPackageResource(js)

    if 'coverage' in options:
        default_template = os.path.join(os.path.dirname(__file__), 'coverage.j2')
        coverage_template = options.get( 'coverage_tpl', default_template)
        try: 
            with open(coverage_template) as src:
                tpl = Template(src.read())
        except IOError:
            log.warning('Coverage template read error, using default template')
            with open(default_template) as src:
                tpl = Template(src.read())


        coverage_target = options.get( 'coverage_target', 'coverage.html')
        outfile = os.path.join(outdir, coverage_target)

        thm_types = [thm.strip() 
                for thm in options.get('coverage_thms', '').split('+')]
        section = options.get('coverage_sectioning', 'chapter')

        def makeCoverageReport(document):
            sections = document.getElementsByTagName(section)
            report = Report([PartialReport.from_section(sec, thm_types) for sec in sections])
            tpl.stream(
                    report=report, 
                    config=document.config,
                    terms=document.context.terms).dump(outfile)
            return [outfile]

        cb = PackageResource(
                renderers=['html5'],
                key='preCleanupCallbacks',
                data=makeCoverageReport)
        css = PackageCss(
                renderers=['html5'],
                package='thmextras',
                data='style_coverage.css')
        js = PackageJs(
                renderers=['html5'],
                package='thmextras',
                data='coverage.js')
        document.addPackageResource([cb, css, js])

    if 'showmore' in options:
        nav = PackageResource(
                renderers=['html5'],
                key='extra-nav',
                data=[
                    {'icon': 'eye-minus',
                    'id': 'showmore-minus',
                    'class': 'showmore'},
                    {'icon': 'eye-plus',
                    'id': 'showmore-plus',
                    'class': 'showmore'}])
        css = PackageCss(
                renderers=['html5'],
                package='thmextras',
                data='showmore.css')
        js = PackageJs(
                renderers=['html5'],
                package='thmextras',
                data='showmore.js')
        js2 = PackageJs(
                renderers=['html5'],
                package='thmextras',
                data='jquery.cookie.js')
        document.addPackageResource([nav, css, js, js2])