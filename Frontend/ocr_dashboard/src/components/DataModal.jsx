import React, { useState, useEffect } from 'react';
import { ExternalLink, Copy, Check, FileCode } from 'lucide-react';

export default function DataModal({ isOpen, title, type, content, onClose }) {
  const [copied, setCopied] = useState(false);
  const [displayUrl, setDisplayUrl] = useState('');

  useEffect(() => {
    if (isOpen && type === 'image' && content) {
      setDisplayUrl(content);
    }
  }, [content, type, isOpen]);

  if (!isOpen) return null;

  const copyToClipboard = (data) => {
    // If it's an object (JSON), stringify it. If it's a string (XML), use as is.
    const textToCopy = typeof data === 'object' ? JSON.stringify(data, null, 2) : data;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-4 border-b bg-slate-50 flex justify-between items-center">
          <h3 className="font-bold text-slate-800 uppercase text-xs tracking-widest">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-red-500 text-3xl font-light transition-colors">&times;</button>
        </div>
        
        <div className="p-6 overflow-y-auto bg-slate-100 flex-grow">
          
          {/* 1. IMAGE VIEW */}
          {type === 'image' && (
            <div className="flex flex-col items-center">
              <div className="bg-white p-4 shadow-xl rounded-xl border border-slate-200 w-full flex justify-center">
                <img 
                  src={displayUrl} 
                  alt="Bill Document" 
                  className="max-w-full h-auto max-h-[65vh] object-contain rounded shadow-md"
                  onError={(e) => {
                    const currentSrc = e.target.src;
                    // Logic to cycle through common extensions if one fails
                    if (currentSrc.endsWith('.jpg')) {
                      e.target.src = currentSrc.replace('.jpg', '.png');
                    } else if (currentSrc.endsWith('.png')) {
                      e.target.src = currentSrc.replace('.png', '.jpeg');
                    } else if (currentSrc.endsWith('.jpeg')) {
                      e.target.src = currentSrc.replace('.jpeg', '.JPG');
                    } else {
                      console.error("All extensions failed for:", displayUrl);
                      e.target.src = "https://placehold.co/600x800?text=File+Not+Found+in+Folder";
                      e.target.onerror = null; 
                    }
                  }}
                />
              </div>
              <div className="mt-6 flex gap-4">
                <a 
                  href={displayUrl} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold shadow-lg hover:bg-blue-700 transition"
                >
                  <ExternalLink size={18} /> View Fullscreen
                </a>
              </div>
            </div>
          )}

          {/* 2. XML VIEW (Tally XML) */}
          {type === 'xml' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button 
                  onClick={() => copyToClipboard(content)} 
                  className="flex items-center gap-2 text-xs font-bold text-amber-600 px-3 py-1 bg-amber-50 rounded-full hover:bg-amber-100 transition"
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied XML!" : "Copy XML"}
                </button>
              </div>
              <div className="bg-slate-900 rounded-xl p-6 shadow-inner border border-slate-700 overflow-x-auto">
                <pre className="text-[12px] leading-relaxed text-amber-200 font-mono whitespace-pre-wrap">
                  {content || "No XML data available."}
                </pre>
              </div>
            </div>
          )}

          {/* 3. JSON VIEW (Extracted & NetSuite Data) */}
          {type === 'json' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button 
                  onClick={() => copyToClipboard(content)} 
                  className="flex items-center gap-2 text-xs font-bold text-blue-600 px-3 py-1 bg-blue-50 rounded-full hover:bg-blue-100 transition"
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied JSON!" : "Copy JSON"}
                </button>
              </div>
              <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                {!content || Object.keys(content).length === 0 ? (
                  <div className="p-10 text-center text-slate-400 italic">No data available for this bill yet.</div>
                ) : (
                  <pre className="text-[12px] leading-relaxed bg-slate-900 text-emerald-400 p-6 rounded-xl overflow-x-auto shadow-inner font-mono">
                    {JSON.stringify(content, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          )}
          
        </div>
      </div>
    </div>
  );
}