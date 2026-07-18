<script lang="ts">
  // Minimal, dependency-free, XSS-safe Markdown renderer for agent/LLM replies.
  // Everything is HTML-escaped first; we then inject only our own tags, so the
  // LLM output can never smuggle markup. Handles the subset LLMs actually emit:
  // fenced + inline code, headings, bold/italic, links, lists, blockquotes.
  let { text = '' }: { text?: string } = $props();

  function escapeHtml(s: string): string {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Inline formatting applied to already-escaped, non-code text.
  function inline(s: string): string {
    // links [text](http(s)://…) — only safe schemes
    s = s.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_m, label, href) =>
        `<a href="${href}" target="_blank" rel="noopener noreferrer" class="underline">${label}</a>`
    );
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
    return s;
  }

  function render(src: string): string {
    const lines = escapeHtml(src ?? '').split('\n');
    const out: string[] = [];
    let i = 0;
    let listType: 'ul' | 'ol' | null = null;

    const closeList = () => {
      if (listType) {
        out.push(`</${listType}>`);
        listType = null;
      }
    };

    while (i < lines.length) {
      const line = lines[i];

      // fenced code block
      const fence = line.match(/^\s*```(\w+)?\s*$/);
      if (fence) {
        closeList();
        const body: string[] = [];
        i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
          body.push(lines[i]);
          i++;
        }
        i++; // skip closing fence
        out.push(
          `<pre class="my-2 overflow-x-auto rounded-lg bg-muted p-3 text-xs"><code>${body.join('\n')}</code></pre>`
        );
        continue;
      }

      // heading
      const h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) {
        closeList();
        const level = h[1].length + 2; // #→h3 … keep it modest in chat
        out.push(`<h${level} class="mt-2 font-semibold">${inline(h[2])}</h${level}>`);
        i++;
        continue;
      }

      // blockquote
      const bq = line.match(/^>\s?(.*)$/);
      if (bq) {
        closeList();
        out.push(
          `<blockquote class="border-l-2 border-border pl-3 italic text-muted-foreground">${inline(bq[1])}</blockquote>`
        );
        i++;
        continue;
      }

      // unordered list
      const ul = line.match(/^\s*[-*+]\s+(.*)$/);
      if (ul) {
        if (listType !== 'ul') {
          closeList();
          out.push('<ul class="my-1 ml-5 list-disc space-y-0.5">');
          listType = 'ul';
        }
        out.push(`<li>${inline(ul[1])}</li>`);
        i++;
        continue;
      }

      // ordered list
      const ol = line.match(/^\s*\d+\.\s+(.*)$/);
      if (ol) {
        if (listType !== 'ol') {
          closeList();
          out.push('<ol class="my-1 ml-5 list-decimal space-y-0.5">');
          listType = 'ol';
        }
        out.push(`<li>${inline(ol[1])}</li>`);
        i++;
        continue;
      }

      // blank line
      if (line.trim() === '') {
        closeList();
        i++;
        continue;
      }

      // paragraph
      closeList();
      out.push(`<p>${inline(line)}</p>`);
      i++;
    }
    closeList();

    // inline code last so it survives the block pass (it never spans lines)
    return out
      .join('\n')
      .replace(/`([^`]+)`/g, '<code class="rounded bg-muted px-1 py-0.5 text-xs">$1</code>');
  }

  const html = $derived(render(text));
</script>

<div class="space-y-1 text-sm leading-relaxed [&_a]:text-primary">
  <!-- eslint-disable-next-line svelte/no-at-html-tags — input is escaped in render() -->
  {@html html}
</div>
