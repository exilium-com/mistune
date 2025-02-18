Changelog
=========

Here is the full history of mistune v3.

Version 3.0.0rc5
----------------

**Released on Mar 22, 2023**

* Fix fenced directives
* Fix inline link parser
* Fix block math plugin for multiple lines
* Fix empty list item for markdown renderer

Version 3.0.0rc4
----------------

**Released on Nov 30, 2022**

* Fix plugin footnotes when there is no newline at the end
* Move safe HTML entities to HTMLRenderer
* Redesign directives parsing
* Add Image and Figure directive

Version 3.0.0rc3
----------------

**Released on Nov 25, 2022**

* Render inline math with ``\(`` and ``\)``
* Added ``RSTRenderer``, and ``MarkdownRenderer``
* Fix ``toc_hook`` method
* **Breaking change**, rename ``RstDirective`` to ``RSTDirective``

Version 3.0.0rc2
----------------

**Released on Nov 6, 2022**

* Add **spoiler** plugin
* Add ``collapse`` option for ``TableOfContents`` directive
* **Breaking change** on directive design, added fenced directive

Version 3.0.0rc1
----------------

**Released on Sep 26, 2022**

* Add **superscript** plugin

Version 3.0.0a3
---------------

**Released on Jul 14, 2022**

* Fix ruby plugin
* Change toc parameter ``depth`` to ``level``

Version 3.0.0a2
---------------

**Released on Jul 13, 2022**

* Escape block code in HTMLRenderer
* Fix parsing links

Version 3.0.0a1
---------------

**Released on Jul 12, 2022**

This is the first release of v3. Features included:

* redesigned mistune
* plugins
* directives
