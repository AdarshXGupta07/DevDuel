import { useState } from "react";

interface CodeEditorProps {
  language: string;
  onSubmit: (code: string) => void;
}

const CodeEditor = ({ language, onSubmit }: CodeEditorProps) => {
  const [code, setCode] = useState("");

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex justify-between mb-2 text-sm text-gray-400">
        <span>Language: {language}</span>
        <span>Editor</span>
      </div>

      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder={`Write your ${language} code here...`}
        className="w-full h-64 bg-gray-800 text-white p-3 rounded outline-none resize-none font-mono"
      />

      <button
        onClick={() => onSubmit(code)}
        className="mt-3 bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded"
      >
        Submit Code
      </button>
    </div>
  );
};

export default CodeEditor;
