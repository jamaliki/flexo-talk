"""A drawing as Office's own shapes on the clipboard: PowerPoint (and Word, and Excel) paste
it as shapes they edit -- boxes, lines joined to them, words -- not as a picture of them.

An Office app copying shapes puts them on the Mac's clipboard as
``com.microsoft.Art--GVML-ClipFormat``: a zip package (OPC), whose one drawing is a
DrawingML locked canvas holding the shapes as a slide's shape tree holds them, but in
DrawingML's own namespace (``a:sp``, ``a:grpSp``, ``a:cxnSp``, ``a:pic``) and each shape's
words in an ``a:txSp``. The package, as PowerPoint 16 for Mac writes it::

    [Content_Types].xml
    _rels/.rels                                 the drawing (a "drawing" relationship)
    clipboard/drawings/drawing1.xml             a:graphic > a:graphicData > lc:lockedCanvas
    clipboard/drawings/_rels/drawing1.xml.rels  the theme, and each picture
    clipboard/theme/theme1.xml                  a:clipboardTheme
    clipboard/media/imageN.png                  the pictures (an SVG beside its PNG)

The shapes are those a PowerPoint export makes of the drawing (``pptx.add_drawing``),
moved from PresentationML into the canvas: so a copy pastes as the deck exports.
"""

from __future__ import annotations

import io
import zipfile
from copy import deepcopy
from xml.sax.saxutils import escape

from flexo.copied import HELD
from flexo.drawing import Drawing, Group, read_drawing
from lxml import etree

from flexo_talk.pptx import _A, _P, _R, EMU_PER_POINT, Placement, add_drawing, plain_names

FORMAT = "com.microsoft.Art--GVML-ClipFormat"
"""The Mac clipboard's name for Office's shapes."""

_LC = "http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpeg", "image/svg+xml": "svg"}

_NON_VISUAL = {
    "sp": ("nvSpPr", "cNvSpPr"),
    "grpSp": ("nvGrpSpPr", "cNvGrpSpPr"),
    "cxnSp": ("nvCxnSpPr", "cNvCxnSpPr"),
    "pic": ("nvPicPr", "cNvPicPr"),
}
"""Each shape's non-visual properties, and the properties of its kind in them: in the canvas
they are as on a slide, without PresentationML's own (``p:nvPr``)."""

THEME = (
    '<a:clipboardTheme xmlns:a="' + _A + '"><a:themeElements>'
    '<a:clrScheme name="Flexo"><a:dk1><a:srgbClr val="000000"/></a:dk1>'
    '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="242126"/></a:dk2>'
    '<a:lt2><a:srgbClr val="F1EFF4"/></a:lt2><a:accent1><a:srgbClr val="1A5D9B"/></a:accent1>'
    '<a:accent2><a:srgbClr val="C0504D"/></a:accent2><a:accent3><a:srgbClr val="4F9B8F"/></a:accent3>'
    '<a:accent4><a:srgbClr val="9A6FB8"/></a:accent4><a:accent5><a:srgbClr val="C9853D"/></a:accent5>'
    '<a:accent6><a:srgbClr val="76707D"/></a:accent6><a:hlink><a:srgbClr val="1A5D9B"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="6B6570"/></a:folHlink></a:clrScheme>'
    '<a:fontScheme name="Flexo"><a:majorFont><a:latin typeface="{family}"/><a:ea typeface=""/>'
    '<a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="{family}"/>'
    '<a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="Flexo"><a:fillStyleLst>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + "</a:fillStyleLst><a:lnStyleLst>"
    + '<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3
    + "</a:lnStyleLst><a:effectStyleLst>"
    + "<a:effectStyle><a:effectLst/></a:effectStyle>" * 3
    + "</a:effectStyleLst><a:bgFillStyleLst>"
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + '</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:clrMap bg1="lt1" tx1="dk1" '
    'bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
    'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    "</a:clipboardTheme>"
)
"""The canvas's theme: its shapes name their colours and faces themselves, so it is only
what an Office app wants to find there -- its words' face the drawing's own."""


def gvml(source: str | Drawing, *, backdrop: str | None = None) -> bytes:
    """The package of Office's shapes for ``source`` (a Flexo SVG, or a drawing read from
    one): every shape as a PowerPoint export makes it, at its size, in the canvas.
    ``backdrop`` is the colour under it, for what is drawn multiplied over it."""

    drawing = read_drawing(source) if isinstance(source, str) else source
    drawing = Drawing(drawing.width, drawing.height, _unheld(drawing.root))
    tree = etree.Element(f"{{{_P}}}spTree", nsmap={"p": _P, "a": _A, "r": _R})
    media: list[tuple[str, bytes, str]] = []

    def add(data: bytes, mime: str) -> str:
        name = f"image{len(media) + 1}.{_EXTENSIONS.get(mime, 'bin')}"
        media.append((name, data, mime))
        return f"rId{len(media) + 1}"

    add.svg = lambda data: add(data, "image/svg+xml")  # type: ignore[attr-defined]
    add_drawing(tree, drawing, Placement(), pictures=add, backdrop=backdrop)
    _named(tree)
    shapes = [shape for shape in (_canvas(child) for child in tree) if shape is not None]
    width = round(drawing.width * EMU_PER_POINT)
    height = round(drawing.height * EMU_PER_POINT)
    canvas = (
        f'<a:graphic xmlns:a="{_A}" xmlns:r="{_R}"><a:graphicData uri="{_LC}">'
        f'<lc:lockedCanvas xmlns:lc="{_LC}"><a:nvGrpSpPr><a:cNvPr id="0" name=""/>'
        f'<a:cNvGrpSpPr/></a:nvGrpSpPr><a:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{width}" cy="{height}"/><a:chOff x="0" y="0"/>'
        f'<a:chExt cx="{width}" cy="{height}"/></a:xfrm></a:grpSpPr></lc:lockedCanvas>'
        f"</a:graphicData></a:graphic>"
    )
    root = etree.fromstring(canvas)
    locked = root.find(f".//{{{_LC}}}lockedCanvas")
    for shape in shapes:
        locked.append(shape)
    etree.cleanup_namespaces(root, top_nsmap={"a": _A, "r": _R})
    drawing_xml = _declared(etree.tostring(root, encoding="UTF-8"))
    family = _family(drawing)
    return _package(drawing_xml, THEME.replace("{family}", escape(family, {'"': "&quot;"})), media)


def _named(tree: etree._Element) -> None:
    """Each shape named as PowerPoint's Selection Pane would name it ("Encoder", "Label
    “Encoder”"), as an export names a slide's (``pptx.plain_names``), not by its id in the
    drawing: a figure's parts copied alone are named so too."""

    plain_names(tree, {})
    for properties in tree.iter(f"{{{_P}}}cNvPr"):
        name = properties.get("name") or ""
        element = properties.getparent().getparent()
        words = " ".join("".join(text.text or "" for text in element.iter(f"{{{_A}}}t")).split())
        holder = next(
            (above.find(f"{{{_P}}}nvGrpSpPr/{{{_P}}}cNvPr") for above in element.iterancestors(f"{{{_P}}}grpSp")), None
        )
        if name.endswith((".label", ".caption")) and words:
            properties.set("name", f"Label \u201c{words[:40]}\u201d")
        elif name.endswith(".body"):
            properties.set("name", holder.get("name") if holder is not None and holder.get("name") else "Shape")


def _unheld(group: Group) -> Group:
    """``group`` with each group in it that only held what was copied (``copied.HELD``: a
    slide's region round the object copied, a figure round its parts) gone, its shapes in
    its place -- as they would be copied in the app."""

    items: list = []
    for item in group.items:
        if not isinstance(item, Group):
            items.append(item)
            continue
        inner = _unheld(item)
        if HELD in item.data and item.clip is None:
            items.extend(inner.items)
        else:
            items.append(inner)
    return Group(group.id, items, dict(group.data), group.label, group.clip)


def _canvas(element: etree._Element) -> etree._Element | None:
    """A shape of a slide's shape tree (``p:sp``...) as the locked canvas holds it."""

    kind = etree.QName(element).localname
    if etree.QName(element).namespace != _P or kind not in _NON_VISUAL:
        return None
    shape = etree.Element(f"{{{_A}}}{kind}")
    own, properties = _NON_VISUAL[kind]
    for child in element:
        name = etree.QName(child).localname
        if name == own:
            shape.append(_non_visual(child, own, properties))
    if kind == "grpSp":
        found = element.find(f"{{{_P}}}grpSpPr")
        if found is not None:
            shape.append(_moved(found))
        for child in element:
            inner = _canvas(child)
            if inner is not None:
                shape.append(inner)
        return shape
    if kind == "pic":
        found = element.find(f"{{{_P}}}blipFill")
        if found is not None:
            shape.append(_moved(found))
    found = element.find(f"{{{_P}}}spPr")
    shape.append(_moved(found) if found is not None else etree.Element(f"{{{_A}}}spPr"))
    body = element.find(f"{{{_P}}}txBody")
    if kind == "sp" and body is not None:
        words = etree.SubElement(shape, f"{{{_A}}}txSp")
        words.append(_moved(body))
        etree.SubElement(words, f"{{{_A}}}useSpRect")
    found = element.find(f"{{{_P}}}style")
    if found is not None:
        shape.append(_moved(found))
    return shape


def _non_visual(element: etree._Element, own: str, properties: str) -> etree._Element:
    out = etree.Element(f"{{{_A}}}{own}")
    for name in ("cNvPr", properties):
        found = element.find(f"{{{_P}}}{name}")
        out.append(_moved(found) if found is not None else etree.Element(f"{{{_A}}}{name}"))
    return out


def _moved(element: etree._Element) -> etree._Element:
    """``element`` (PresentationML's) in DrawingML's namespace, with what it holds."""

    out = etree.Element(f"{{{_A}}}{etree.QName(element).localname}", dict(element.attrib))
    out.text = element.text
    for child in element:
        out.append(deepcopy(child))
    return out


def _family(drawing: Drawing) -> str:
    from flexo.drawing import Text

    for item in drawing.walk():
        if isinstance(item, Text) and item.family:
            return item.family.split(",")[0].strip().strip("'\"")
    return "Calibri"


def _declared(xml: bytes) -> bytes:
    if xml.startswith(b"<?xml"):
        xml = xml.split(b"?>", 1)[1]
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml


def _package(drawing_xml: bytes, theme: str, media: list[tuple[str, bytes, str]]) -> bytes:
    defaults = {"rels": "application/vnd.openxmlformats-package.relationships+xml", "xml": "application/xml"}
    for name, _, mime in media:
        defaults.setdefault(name.rsplit(".", 1)[1], mime)
    types = "".join(f'<Default Extension="{ext}" ContentType="{kind}"/>' for ext, kind in defaults.items())
    content_types = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="{_TYPES}">{types}'
        '<Override PartName="/clipboard/drawings/drawing1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
        '<Override PartName="/clipboard/theme/theme1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>'
    )
    package_rels = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{_PACKAGE_REL}">'
        f'<Relationship Id="rId1" Type="{_REL}/drawing" Target="clipboard/drawings/drawing1.xml"/>'
        "</Relationships>"
    )
    related = [f'<Relationship Id="rId1" Type="{_REL}/theme" Target="../theme/theme1.xml"/>']
    related += [
        f'<Relationship Id="rId{index + 2}" Type="{_REL}/image" Target="../media/{name}"/>'
        for index, (name, _, _) in enumerate(media)
    ]
    drawing_rels = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{_PACKAGE_REL}">'
        + "".join(related)
        + "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", package_rels)
        package.writestr("clipboard/drawings/_rels/drawing1.xml.rels", drawing_rels)
        package.writestr("clipboard/drawings/drawing1.xml", drawing_xml)
        package.writestr(
            "clipboard/theme/theme1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + theme
        )
        for name, data, _ in media:
            package.writestr(f"clipboard/media/{name}", data)
    return buffer.getvalue()
