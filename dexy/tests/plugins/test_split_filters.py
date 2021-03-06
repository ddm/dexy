from dexy.tests.utils import wrap
from dexy.node import DocNode

def test_split_html_filter():
    with wrap() as wrapper:
        contents="""
        <p>This is at the top.</p>
        <!-- split "a-page" -->
        some content on a page
        <!-- split "another-page" -->
        some content on another page
        <!-- endsplit -->
        bottom
        """

        node = DocNode("subdir/example.html|splithtml", contents=contents, wrapper=wrapper)
        wrapper.run_docs(node)

        assert node.children[1].key == "subdir/a-page.html"
        assert node.children[2].key == "subdir/another-page.html"

        doc = node.children[0]
        od = doc.output().data()

        assert "<p>This is at the top.</p>" in od
        assert '<a href="a-page.html">' in od
        assert '<a href="another-page.html">' in od
        assert "bottom" in od

        assert "<p>This is at the top.</p>" in node.children[1].output().data()
        assert "some content on a page" in node.children[1].output().data()
        assert "bottom" in node.children[1].output().data()

        assert "<p>This is at the top.</p>" in node.children[2].output().data()
        assert "some content on another page" in node.children[2].output().data()
        assert "bottom" in node.children[2].output().data()

def test_split_html_additional_filters():
    with wrap() as wrapper:
        contents="""
        <p>This is at the top.</p>
        <!-- split "a-page" -->
        some content on a page
        <!-- split "another-page" -->
        some content on another page
        <!-- endsplit -->
        bottom
        """

        node = DocNode("example.html|splithtml",
                contents=contents,
                splithtml = { "keep-originals" : False, "additional-doc-filters" : "processtext" },
                wrapper=wrapper
              )
        wrapper.run_docs(node)

        doc = node.children[0]

        assert node.children[1].key == "a-page.html|processtext"
        assert node.children[2].key == "another-page.html|processtext"

        od = doc.output().data()
        assert "<p>This is at the top.</p>" in od
        assert '<a href="a-page.html">' in od
        assert '<a href="another-page.html">' in od
        assert "bottom" in od

        a_page = node.children[1]
        a_page_data = a_page.output().data()
        assert "<p>This is at the top.</p>" in a_page_data
        assert "some content on a page" in a_page_data
        assert "bottom" in a_page_data
        assert "Dexy processed the text" in a_page_data

        another_page = node.children[2]
        another_page_data = another_page.output().data()
        assert "<p>This is at the top.</p>" in another_page_data
        assert "some content on another page" in another_page_data
        assert "bottom" in another_page_data
        assert "Dexy processed the text" in another_page_data
