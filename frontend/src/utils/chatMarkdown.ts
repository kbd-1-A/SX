import MarkdownIt from 'markdown-it'

const messageTimePrefix = /^\s*\[消息时间：[^\]\r\n]*\]\s*(?:\r?\n|$)/u

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: false,
})

markdown.renderer.rules.link_open = (tokens, index, options, _env, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

export function normalizeAssistantMarkdown(content: string): string {
  let normalized = content
  while (messageTimePrefix.test(normalized)) {
    normalized = normalized.replace(messageTimePrefix, '')
  }

  // 兼容模型偶尔在加粗标记内侧多输出的空格，例如 **标题 **。
  return normalized
    .replace(/\*\*[ \t]+(?=\S)/g, '**')
    .replace(/(\S)[ \t]+\*\*/g, '$1**')
}

export function renderAssistantMarkdown(content: string): string {
  return markdown.render(normalizeAssistantMarkdown(content))
}
