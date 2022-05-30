import re
from .util import (
    unikey,
    escape,
    escape_url,
    safe_entity,
    strip_end,
    expand_tab,
    expand_leading_tab,
)
from .state import BlockState
from .helpers import (
    LINK_LABEL,
    HTML_TAGNAME,
    HTML_ATTRIBUTES,
    BLOCK_TAGS,
    PRE_TAGS,
    unescape_char,
    parse_link_href,
    parse_link_title,
)

_INDENT_CODE_TRIM = re.compile(r'^ {1,4}', flags=re.M)
_AXT_HEADING_TRIM = re.compile(r'(\s+|^)#+\s*$')
_BLOCK_QUOTE_TRIM = re.compile(r'^ {0,1}', flags=re.M)
_BLOCK_QUOTE_LEADING = re.compile(r'^ *>', flags=re.M)

_LINE_BLANK_END = re.compile(r'\n[ \t]*\n$')
_LINE_HAS_TEXT = re.compile(r'( *)\S')
_BLANK_TO_LINE = re.compile(r'[ \t]*\n')

_BLOCK_TAGS_PATTERN = '|'.join(BLOCK_TAGS) + '|' + '|'.join(PRE_TAGS)
_BLOCK_HTML_BREAK = re.compile(
    r' {0,3}(?:'
    r'(?:</?' + '|'.join(BLOCK_TAGS) + '|' + '|'.join(PRE_TAGS) + r'(?:[ \t]+|\n|$))'
    r'|<!--' # comment
    r'|<\?'  # script
    r'|<![A-Z]'
    r'|<!\[CDATA\[)'
)
_OPEN_TAG_END = re.compile(HTML_ATTRIBUTES + r'[ \t]*>[ \t]*(?:\n|$)')
_CLOSE_TAG_END = re.compile(r'[ \t]*>[ \t]*(?:\n|$)')


class BlockParser:
    state_cls = BlockState

    BLANK_LINE = re.compile(r'(^[ \t\v\f]*\n)+', re.M)
    STRICT_BLOCK_QUOTE = re.compile(r'( {0,3}>[^\n]*(?:\n|$))+')

    LIST = (
        r'^(?P<list_1> {0,3})'
        r'(?P<list_2>[\*\+-]|\d{1,9}[.)])'
        r'(?P<list_3>[ \t]*|[ \t].+)$'
    )

    INDENT_CODE = (
        r'(?: {4}| *\t)[^\n]+(?:\n+|$)'
        r'((?:(?: {4}| *\t)[^\n]+(?:\n+|$))|\s)*'
    )

    FENCED_CODE = (
        r'^(?P<fenced_1> {0,3})(?P<fenced_2>`{3,}|~{3,})'
        r'[ \t]*(?P<fenced_3>.*?)$'
    )

    RAW_HTML = (
        r'^ {0,3}('
        r'</?' + HTML_TAGNAME + r'|'
        r'<!--|' # comment
        r'<\?|'  # script
        r'<![A-Z]|'
        r'<!\[CDATA\[)'
    )

    BLOCK_HTML = (
        r'^ {0,3}(?:'
        r'(?:</?' + _BLOCK_TAGS_PATTERN + r'(?:[ \t]+|\n|$))'
        r'|<!--' # comment
        r'|<\?'  # script
        r'|<![A-Z]'
        r'|<!\[CDATA\[)'
    )

    SPECIFICATION = {
        'blank_line': r'(^[ \t\v\f]*\n)+',
        'axt_heading': r'^ {0,3}(?P<axt_1>#{1,6})(?!#+)(?P<axt_2>[ \t]*|[ \t]+.*?)$',
        'setex_heading': r'^ {0,3}(?P<setext_1>=|-){1,}[ \t]*$',
        'fenced_code': FENCED_CODE,
        'indent_code': INDENT_CODE,
        'thematic_break': r'^ {0,3}((?:-[ \t]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})$',
        'ref_link': r'^ {0,3}\[(?P<link_1>' + LINK_LABEL + r')\]:',
        'block_quote': r' {0,3}>(?P<quote_1>.*?)$',
        'list': LIST,
        'block_html': BLOCK_HTML,
        'raw_html': RAW_HTML,
    }

    RULE_NAMES = (
        'blank_line',
        'fenced_code',
        'indent_code',
        'axt_heading',
        'setex_heading',
        'thematic_break',
        'block_quote',
        # 'list',
        'ref_link',
        'raw_html',
    )

    def __init__(self, rules=None, block_quote_rules=None, list_rules=None,
                 max_nested_level=6):
        self.specification = self.SPECIFICATION.copy()

        if rules is None:
            rules = list(self.RULE_NAMES)

        if block_quote_rules is None:
            block_quote_rules = list(self.RULE_NAMES)

        if list_rules is None:
            list_rules = list(self.RULE_NAMES)

        self.rules = rules

        self.block_quote_rules = block_quote_rules
        self.list_rules = list_rules
        self.max_nested_level = max_nested_level

        self.__sc = {}
        # register default parse methods
        self.__methods = {
            name: getattr(self, 'parse_' + name) for name in self.RULE_NAMES
        }

    def compile_sc(self, rules):
        if rules is None:
            key = '$'
            rules = self.rules
        else:
            key = '|'.join(rules)

        sc = self.__sc.get(key)
        if sc:
            return sc

        regex = '|'.join(r'(?P<%s>%s)' % (k, self.specification[k]) for k in rules)
        sc = re.compile(regex, re.M)
        self.__sc[key] = sc
        return sc

    def register_rule(self, name, func, before=None):
        self.__methods[name] = lambda state: func(self, state)
        if before:
            index = self.rules.index(before)
            self.rules.insert(index, name)
        else:
            self.rules.append(name)

    def parse_method(self, m, state):
        func = self.__methods[m.lastgroup]
        return func(m, state)

    def parse_blank_line(self, m, state):
        state.append_token({'type': 'blank_line'})
        return m.end()

    def parse_thematic_break(self, m, state):
        state.append_token({'type': 'thematic_break'})
        # $ does not count '\n'
        return m.end() + 1

    def parse_indent_code(self, m, state):
        # it is a part of the paragraph
        end_pos = state.append_paragraph()
        if end_pos:
            return end_pos

        code = m.group('indent_code')
        code = expand_leading_tab(code)
        code = _INDENT_CODE_TRIM.sub('', code)
        line_count = code.count('\n')
        code = escape(code.strip('\n'))
        state.append_token({'type': 'block_code', 'raw': code})
        return m.end()

    def parse_fenced_code(self, m, state):
        spaces = m.group('fenced_1')
        marker = m.group('fenced_2')
        info = m.group('fenced_3')

        c = marker[0]
        if info and c == '`':
            # CommonMark Example 145
            # Info strings for backtick code blocks cannot contain backticks
            if info.find(c) != -1:
                return

        _end = re.compile(
            r'^ {0,3}' + c + '{' + str(len(marker)) + r',}[ \t]*(?:\n|$)', re.M)
        cursor_start = m.end()

        m2 = _end.search(state.src, cursor_start)
        if m2:
            code = state.src[cursor_start:m2.start()]
            end_pos = m2.end()
        else:
            code = state.src[cursor_start:]
            end_pos = state.cursor_max

        if spaces and code:
            _trim_pattern = re.compile('^ {0,' + str(len(spaces)) + '}', re.M)
            code = _trim_pattern.sub('', code)

        token = {'type': 'block_code', 'raw': escape(code), 'fenced': True}
        if info:
            info = unescape_char(info)
            token['attrs'] = {'info': safe_entity(info.strip())}

        state.append_token(token)
        return end_pos

    def parse_axt_heading(self, m, state):
        level = len(m.group('axt_1'))
        text = m.group('axt_2').strip()
        # remove last #
        if text:
            text = _AXT_HEADING_TRIM.sub('', text)

        token = {'type': 'heading', 'text': text, 'attrs': {'level': level}}
        state.append_token(token)
        return m.end() + 1

    def parse_setex_heading(self, m, state):
        last_token = state.last_token()
        if last_token and last_token['type'] == 'paragraph':
            level = 1 if m.group('setext_1') == '=' else 2
            last_token['type'] = 'heading'
            last_token['attrs'] = {'level': level}
            return m.end() + 1

    def parse_ref_link(self, m, state):
        end_pos = state.append_paragraph()
        if end_pos:
            return end_pos

        key = unikey(m.group('link_1'))
        if not key:
            return

        href, href_pos = parse_link_href(state.src, m.end(), block=True)
        if href is None:
            return

        _blank = self.BLANK_LINE.search(state.src, href_pos)
        if _blank:
            max_pos = _blank.start()
        else:
            max_pos = state.cursor_max

        title, title_pos = parse_link_title(state.src, href_pos, max_pos)
        if title_pos:
            m = _BLANK_TO_LINE.match(state.src, title_pos)
            if m:
                title_pos = m.end()
            else:
                title_pos = None
                title = None

        if title_pos is None:
            m = _BLANK_TO_LINE.match(state.src, href_pos)
            if m:
                href_pos = m.end()
            else:
                href_pos = None
                href = None

        end_pos = title_pos or href_pos
        if not end_pos:
            return

        if key not in state.env['ref_links']:
            href = unescape_char(href)
            attrs = {'url': escape_url(href)}
            if title:
                attrs['title'] = safe_entity(title)
            state.env['ref_links'][key] = attrs
        return end_pos

    def parse_block_quote(self, m, state):
        # cleanup at first to detect if it is code block
        text = m.group('quote_1') + '\n'
        text = expand_leading_tab(text, 3)
        text = _BLOCK_QUOTE_TRIM.sub('', text)

        sc = self.compile_sc(['blank_line', 'indent_code', 'fenced_code'])
        require_marker = bool(sc.match(text))

        state.cursor = m.end() + 1

        end_pos = None
        if require_marker:
            m = state.match(self.STRICT_BLOCK_QUOTE)
            if m:
                quote = m.group(0)
                quote = _BLOCK_QUOTE_LEADING.sub('', quote)
                quote = expand_leading_tab(quote, 3)
                quote = _BLOCK_QUOTE_TRIM.sub('', quote)
                text += quote
                state.cursor = m.end()
        else:
            prev_blank_line = False

            # break_rules = ['blank_line', 'thematic_break', 'fenced_code', 'list']
            break_rules = ['blank_line', 'thematic_break', 'fenced_code']
            break_sc = self.compile_sc([
                'blank_line', 'thematic_break', 'fenced_code', # 'list',
                'block_html',
            ])
            while state.cursor < state.cursor_max:
                m = state.match(self.STRICT_BLOCK_QUOTE)
                if m:
                    quote = m.group(0)
                    quote = _BLOCK_QUOTE_LEADING.sub('', quote)
                    quote = expand_leading_tab(quote, 3)
                    quote = _BLOCK_QUOTE_TRIM.sub('', quote)
                    text += quote
                    state.cursor = m.end()
                    if not quote.strip():
                        prev_blank_line = True
                    else:
                        prev_blank_line = bool(_LINE_BLANK_END.search(quote))
                    continue

                if prev_blank_line:
                    # CommonMark Example 249
                    # because of laziness, a blank line is needed between
                    # a block quote and a following paragraph
                    break

                m = state.match(break_sc)
                end_pos = self.parse_method(m, state)
                if end_pos:
                    break

                # lazy continuation line
                pos = self.find_line_end()
                line = self.get_text(pos)
                line = expand_leading_tab(line, 3)
                text += line
                state.cursor = pos

        # according to CommonMark Example 6, the second tab should be
        # treated as 4 spaces
        text = expand_tab(text)

        # scan children state
        child = self.state_cls(state)
        child.in_block = 'block_quote'
        child.process(text)

        if state.depth() >= self.max_nested_level:
            rules = list(self.block_quote_rules)
            rules.remove('block_quote')
        else:
            rules = self.block_quote_rules

        self.parse(child, rules)
        token = {'type': 'block_quote', 'children': child.tokens}
        if end_pos:
            state.prepend_token(token)
            return end_pos
        state.append_token(token)
        return state.cursor

    def parse_list(self, m, state):
        text = m.group('list_3')
        if not text.strip():
            # Example 285
            # an empty list item cannot interrupt a paragraph
            end_pos = state.append_paragraph()
            if end_pos:
                return end_pos

        marker = m.group('list_2')
        ordered = len(marker) > 1
        attrs = {'ordered': ordered}
        if ordered:
            start = int(marker[:-1])
            if start != 1:
                # Example 304
                # we allow only lists starting with 1 to interrupt paragraphs
                end_pos = state.append_paragraph()
                if end_pos:
                    return end_pos
                attrs['start'] = start

        depth = state.depth()
        if depth >= self.max_nested_level:
            rules = list(self.list_rules)
            rules.remove('list')
        else:
            rules = self.list_rules

        children = []
        while m:
            m = self._parse_list_item(state, m, children, rules)

        attrs['depth'] = depth
        attrs['tight'] = state.list_tight
        for tok in children:
            tok['attrs'] = {'depth': depth, 'tight': state.list_tight}

        token = {
            'type': 'list',
            'children': children,
            'attrs': attrs,
        }
        state.add_token(token)
        # reset list_tight
        state.list_tight = True
        return True

    def _parse_list_item(self, parent_state, match, children, rules):
        has_next = False
        line_root = parent_state.line
        start_line = line_root + parent_state.line_root

        space_width = len(match.group(1))
        marker = match.group(2)
        leading_width = space_width + len(marker)

        bullet = _get_list_bullet(marker[-1])
        item_pattern = _compile_list_item_pattern(bullet, leading_width)
        text, continue_width = _compile_continue_width(match.group(3), leading_width)

        pairs = [
            ('thematic_break', self.THEMATIC_BREAK.pattern),
            ('fenced_code', self.FENCED_CODE.pattern),
            ('axt_heading', self.AXT_HEADING.pattern),
            ('block_quote', self.BLOCK_QUOTE.pattern),
            ('block_html', _BLOCK_HTML_BREAK.pattern),
            ('list', self.LIST.pattern),
        ]
        if leading_width < 3:
            _repl_w = str(leading_width)
            pairs = [(n, p.replace('3', _repl_w, 1)) for n, p in pairs]

        pairs.insert(1, ('list_item', item_pattern))
        if text:
            break_pattern = (
                r'[ \t]*\n'
                r' {0,' + str(continue_width - 1) + r'}(?!' + bullet + r')'
                r'\S'
            )
        else:
            break_pattern = r'[ \t]*\n( {0,3}(?!' + bullet + r')| {4,}| *\t)\S'
        pairs.append(('break', break_pattern))

        sc = re.compile('|'.join(r'(?P<%s>(?<=\n)%s)' % pair for pair in pairs))
        m = sc.search(parent_state.src, match.end())
        if m:
            tok_type = m.lastgroup
            cursor = m.start()
            src = parent_state.src[match.end():cursor]
            line_count = src.count('\n') + 1
            parent_state.line += line_count
            parent_state.cursor = cursor
            if tok_type == 'list_item':
                has_next = True
            elif tok_type != 'break':
                func = getattr(self, 'parse_' + tok_type)
                func(parent_state)
        else:
            src = parent_state.src[match.end():]
            line_count = src.count('\n') + 1
            parent_state.line += line_count
            parent_state.cursor = parent_state.cursor_max

        state = self.state_cls(parent_state)
        state.line_root = line_root
        text = _clean_list_item_text(src, text, continue_width)

        if parent_state.list_tight and _LINE_BLANK_END.search(text):
            parent_state.list_tight = False

        state.process(strip_end(text))
        self.parse(state, rules)

        if parent_state.list_tight:
            if any((tok['type'] == 'blank_line' for tok in state.tokens)):
                parent_state.list_tight = False

        children.append({
            'type': 'list_item',
            'start_line':start_line,
            'end_line': start_line + line_count,
            'children': state.tokens,
        })
        if has_next:
            pattern = re.compile(item_pattern)
            return parent_state.match(pattern)

    def parse_block_html(self, m, state):
        return self.parse_raw_html(m, state)

    def parse_raw_html(self, m, state):
        marker = m.group(m.lastgroup).strip()

        # rule 2
        if marker == '<!--':
            return _parse_html_to_end(state, '-->', m.end())

        # rule 3
        if marker == '<?':
            return _parse_html_to_end(state, '?>', m.end())

        # rule 5
        if marker == '<![CDATA[':
            return _parse_html_to_end(state, ']]>', m.end())

        # rule 4
        if marker.startswith('<!'):
            return _parse_html_to_end(state, '>', m.end())

        close_tag = None
        open_tag = None
        if marker.startswith('</'):
            close_tag = marker[2:].lower()
            # rule 6
            if close_tag in BLOCK_TAGS:
                return _parse_html_to_newline(state, self.BLANK_LINE)
        else:
            open_tag = marker[1:].lower()
            # rule 1
            if open_tag in PRE_TAGS:
                end_tag = '</' + open_tag + '>'
                return _parse_html_to_end(state, end_tag, m.end())
            # rule 6
            if open_tag in BLOCK_TAGS:
                return _parse_html_to_newline(state, self.BLANK_LINE)

        # Blocks of type 7 may not interrupt a paragraph.
        end_pos = state.append_paragraph()
        if end_pos:
            return end_pos

        # rule 7
        start_pos = m.end()
        end_pos = state.find_line_end()
        text = state.get_text(end_pos)
        if (open_tag and _OPEN_TAG_END.match(state.src, start_pos, end_pos)) or \
           (close_tag and _CLOSE_TAG_END.match(state.src, start_pos, end_pos)):
            return _parse_html_to_newline(state, self.BLANK_LINE)

    def parse_paragraph(self, state):
        if not state.append_paragraph():
            line = state.get_line()
            state.add_token({'type': 'paragraph', 'text': line}, 1)
        return True

    def postprocess_paragraph(self, token, parent):
        """A method to post process paragraph token. Developers CAN
        subclass BlockParser and rewrite this method to update the
        common paragraph token."""
        attrs = parent.get('attrs')
        if attrs and attrs.get('tight'):
            token['type'] = 'block_text'

    def parse(self, state, rules=None):
        sc = self.compile_sc(rules)

        while state.cursor < state.cursor_max:
            m = sc.search(state.src, state.cursor)
            if not m:
                break

            end_pos = m.start()
            if end_pos > state.cursor:
                text = state.get_text(end_pos)
                state.add_paragraph(text)
                state.cursor = end_pos

            end_pos = self.parse_method(m, state)
            if end_pos:
                state.cursor = end_pos
            else:
                end_pos = state.find_line_end()
                state.add_paragraph(state.get_text(pos))
                state.cursor = end_pos

        if state.cursor < state.cursor_max:
            text = state.src[state.cursor:]
            state.add_paragraph(text)
            state.cursor = state.cursor_max

    def render(self, state, inline):
        return self._call_render(state.tokens, state, inline)

    def _scan_rules(self, state, rules):
        for name in rules:
            func = self.__methods[name]
            if func(state):
                return
        self.parse_paragraph(state)

    def _call_render(self, tokens, state, inline, parent=None):
        data = self._iter_render(tokens, state, inline, parent)
        if inline.renderer:
            return inline.renderer(data)
        return list(data)

    def _iter_render(self, tokens, state, inline, parent):
        for tok in tokens:
            if 'children' in tok:
                children = self._call_render(tok['children'], state, inline, tok)
                tok['children'] = children
            elif 'text' in tok:
                text = tok.pop('text')
                children = inline(text.strip(), state.env)
                tok['children'] = children
                if tok['type'] == 'paragraph' and parent:
                    self.postprocess_paragraph(tok, parent)
            yield tok


def _get_list_bullet(c):
    if c == '.':
        bullet = r'\d{0,9}\.'
    elif c == ')':
        bullet = r'\d{0,9}\)'
    elif c == '*':
        bullet = r'\*'
    elif c == '+':
        bullet = r'\+'
    else:
        bullet = '-'
    return bullet


def _compile_list_item_pattern(bullet, leading_width):
    if leading_width > 3:
        leading_width = 3
    return (
        r'( {0,' + str(leading_width) + '})'
        r'(' + bullet + ')'
        r'([ \t]*|[ \t][^\n]+)(?:\n|$)'
    )


def _compile_continue_width(text, leading_width):
    text = expand_leading_tab(text, 3)
    text = expand_tab(text)

    m2 = _LINE_HAS_TEXT.match(text)
    if m2:
        # indent code, startswith 5 spaces
        if text.startswith('     '):
            space_width = 1
        else:
            space_width = len(m2.group(1))

        text = text[space_width:]
    else:
        space_width = 1
        text = ''

    continue_width = leading_width + space_width
    return text, continue_width



def _clean_list_item_text(src, text, continue_width):
    # according to Example 7, tab should be treated as 3 spaces
    if text:
        rv = [text]
    else:
        rv = []

    trim_space = ' ' * continue_width
    lines = src.split('\n')
    for line in lines:
        if line.startswith(trim_space):
            line = line.replace(trim_space, '', 1)
            # according to CommonMark Example 5
            # tab should be treated as 4 spaces
            line = expand_tab(line)
            rv.append(line)
        else:
            rv.append(line)

    return '\n'.join(rv)


def _parse_html_to_end(state, end_marker, start_pos):
    marker_pos = state.src.find(end_marker, start_pos)
    if marker_pos == -1:
        text = state.src[state.cursor:]
        end_pos = state.cursor_max
    else:
        text = state.get_text(marker_pos)
        state.cursor = marker_pos
        end_pos = state.find_line_end()
        text += state.get_text(end_pos)

    state.append_token({'type': 'block_html', 'raw': text})
    return end_pos


def _parse_html_to_newline(state, newline):
    m = newline.search(state.src, state.cursor)
    if m:
        end_pos = m.start()
        text = state.get_text(end_pos)
    else:
        text = state.src[state.cursor:]
        end_pos = state.cursor_max

    state.append_token({'type': 'block_html', 'raw': text})
    return end_pos
