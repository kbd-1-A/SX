import { describe, expect, it } from 'vitest'
import { normalizeAssistantMarkdown, renderAssistantMarkdown } from './chatMarkdown'

describe('assistant Markdown rendering', () => {
  it('removes repeated legacy message-time prefixes', () => {
    const content = [
      '[消息时间：2026-08-10 17:26:42 +0800]',
      '[消息时间：2026-08-10 17:26:31 +0800]',
      '正文',
    ].join('\n')

    expect(normalizeAssistantMarkdown(content)).toBe('正文')
  })

  it('renders bold text even when the closing marker has an inner space', () => {
    expect(renderAssistantMarkdown('**热门前列（常年霸榜） **')).toContain(
      '<strong>热门前列（常年霸榜）</strong>',
    )
  })

  it('escapes raw HTML from model output', () => {
    const rendered = renderAssistantMarkdown('<script>alert(1)</script>')

    expect(rendered).not.toContain('<script>')
    expect(rendered).toContain('&lt;script&gt;')
  })
})
