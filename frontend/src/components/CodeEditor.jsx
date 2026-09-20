import Editor from '@monaco-editor/react';
import { useEffect, useRef } from 'react';

// Our language ids → Monaco's. They mostly match; cpp and java are the exceptions.
const LANGUAGE_IDS = {
  python: 'python',
  javascript: 'javascript',
  cpp: 'cpp',
  java: 'java',
};

/**
 * The ranked editor, with anti-cheat Layer 1 attached.
 *
 * Two honest caveats, both worth knowing before trusting any of this:
 *  - Paste-disable stops casual cheating (alt-tab to ChatGPT, ctrl-V). Anyone with
 *    devtools bypasses it in seconds. It is a speed bump, not a wall.
 *  - Which is exactly why the keystroke log matters more: typed code has a rhythm,
 *    pasted-then-edited code does not, and that signal survives devtools.
 */
export default function CodeEditor({
  value,
  onChange,
  language = 'python',
  ranked = false,
  onEvent,
  readOnly = false,
}) {
  const editorRef = useRef(null);
  const seqRef = useRef(0);
  const bufferRef = useRef([]);

  // Batch behavioural events and flush every 2s. One row per keystroke over the wire
  // would be ~5 events/sec/player of chat traffic for no benefit.
  useEffect(() => {
    if (!onEvent) return undefined;
    const id = setInterval(() => {
      if (bufferRef.current.length === 0) return;
      const batch = bufferRef.current;
      bufferRef.current = [];
      onEvent(batch);
    }, 2000);
    return () => clearInterval(id);
  }, [onEvent]);

  function record(kind, payload) {
    if (!onEvent) return;
    bufferRef.current.push({ seq: seqRef.current++, kind, payload });
  }

  function handleMount(editor, monaco) {
    editorRef.current = editor;

    if (ranked) {
      // Block paste (bringing an answer in) and copy/cut (taking the problem out to an
      // LLM). Copy matters more than people expect: the fastest cheat is not pasting a
      // solution in, it is copying the statement out.
      editor.onKeyDown((e) => {
        const mod = e.ctrlKey || e.metaKey;
        if (!mod) return;
        const blocked = {
          [monaco.KeyCode.KeyV]: 'paste_attempt',
          [monaco.KeyCode.KeyC]: 'copy_attempt',
          [monaco.KeyCode.KeyX]: 'cut_attempt',
        }[e.keyCode];
        if (blocked) {
          e.preventDefault();
          e.stopPropagation();
          record(blocked, { via: 'keyboard' });
        }
      });

      // The DOM events cover right-click → Paste/Copy and any path that bypasses
      // Monaco's own keybindings.
      const dom = editor.getDomNode();
      ['paste', 'copy', 'cut'].forEach((type) => {
        dom?.addEventListener(type, (e) => {
          e.preventDefault();
          e.stopPropagation();
          record(`${type}_attempt`, { via: 'dom_event' });
        });
      });
    }

    editor.onDidChangeModelContent((event) => {
      for (const change of event.changes) {
        // A large insert in a single change event is the signature of a paste that got
        // through some other way. Log it; do not block it — false positives here would
        // punish someone duplicating a function.
        if (change.text.length > 80) {
          record('large_insert', { length: change.text.length });
        }
      }
      record('keystroke_batch', { changes: event.changes.length, at: Date.now() });
    });

    editor.onDidBlurEditorWidget(() => record('blur', { at: Date.now() }));
    editor.onDidFocusEditorWidget(() => record('focus', { at: Date.now() }));
  }

  return (
    <div className="editor-wrap">
      <Editor
        height="100%"
        theme="vs-dark"
        language={LANGUAGE_IDS[language] || 'python'}
        value={value}
        onChange={(v) => onChange(v ?? '')}
        onMount={handleMount}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          tabSize: 4,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          readOnly,
          contextmenu: !ranked,
          quickSuggestions: !ranked,
        }}
      />
    </div>
  );
}
