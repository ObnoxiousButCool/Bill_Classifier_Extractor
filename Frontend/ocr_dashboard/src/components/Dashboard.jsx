import React, { useState, useEffect } from 'react';
import { FileJson, Eye, RefreshCw } from 'lucide-react';
import DataModal from './DataModal';

export default function BillDashboard() {
  const [bills, setBills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalConfig, setModalConfig] = useState({ isOpen: false, data: null, title: '', type: '' });

  const PYTHON_BACKEND_URL = "/api-remote";

  const formatDateTime = (isoString) => {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString('en-GB', { 
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: true 
    });
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const targetUrl = `${PYTHON_BACKEND_URL}/`;
      const response = await fetch(targetUrl);
      
      if (!response.ok) {
        console.error(`Backend Error: ${response.status}`);
        return;
      }

      const data = await response.json();
      console.log("Verified Data Structure:", data);

      // KEY FIX: Backend sends { "bills": [...], "count": X }
      // We need to access data.bills
      if (data && data.bills) {
        setBills(data.bills);
      } else if (Array.isArray(data)) {
        setBills(data);
      } else {
        setBills([]);
      }
    } catch (err) {
      console.error("Fetch Error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openModal = (data, title, type) => {
    setModalConfig({ isOpen: true, data, title, type });
  };

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <div className="max-w-7xl mx-auto mb-6 flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-800">Bill Processing Dashboard</h1>
        <button onClick={fetchData} className="flex items-center gap-2 px-4 py-2 bg-white border rounded-lg shadow-sm hover:bg-gray-50 text-sm font-semibold transition">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Refresh Data
        </button>
      </div>

      <div className="max-w-7xl mx-auto bg-white shadow-xl rounded-xl overflow-hidden border border-gray-200">
        <table className="w-full text-left border-collapse">
          <thead className="bg-slate-900 text-white">
            <tr>
              <th className="p-4 text-xs font-bold uppercase tracking-wider">Document ID</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider">Created At</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider">Type of bill</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-center">Extracted JSON</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-center">NetSuite JSON</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-center">Tally XML</th>
              <th className="p-4 text-xs font-bold uppercase tracking-wider text-center">Bill Image</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {bills.map((bill) => (
              <tr key={bill.bill_id} className="hover:bg-slate-50 border-b border-slate-100 transition-colors">
                <td className="p-4 font-mono text-[10px] text-slate-500">{bill.bill_id}</td>
                <td className="p-4 text-[12px] text-slate-600 font-medium">{formatDateTime(bill.created_at)}</td>
                <td className="p-4">
                  <div className="flex flex-col">
                    <span className="text-sm font-semibold text-slate-700">{bill.bill_type}</span>
                    <span className="text-[11px] text-slate-400 italic">{bill.bill_subtype || 'N/A'}</span>
                  </div>
                </td>
                
                {/* Extracted JSON */}
                <td className="p-4 text-center">
                  <button 
                    onClick={() => openModal(bill.extracted_json, 'Extracted Data', 'json')}
                    className="p-2 bg-emerald-50 text-emerald-700 rounded-lg hover:bg-emerald-100"
                  >
                    <FileJson size={18} />
                  </button>
                </td>

                {/* NetSuite JSON */}
                <td className="p-4 text-center">
                  <button 
                    onClick={() => openModal(bill.netsuite_json, 'NetSuite Payload', 'json')}
                    className="p-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100"
                  >
                    <FileJson size={18} />
                  </button>
                </td>

                <td className="p-4 text-center">
                  <button 
                    onClick={() => openModal(bill.tally_xml, 'Tally XML Export', 'xml')}
                    className="p-2 bg-amber-50 text-amber-700 rounded-lg hover:bg-amber-100 transition-colors"
                  >
                    <ClipboardList size={18} /> {/* Using ClipboardList icon for XML */}
                  </button>
                </td>

                {/* Bill Image - LOCAL PATH LOGIC */}
                <td className="p-4 text-center">
                  <button 
                    onClick={() => {
                      // Uses the bill_id and looks at your local python server on port 9000
                      const localUrl = `http://localhost:9000/${bill.bill_id}.jpg`;
                      openModal(localUrl, 'Original Bill', 'image');
                    }}
                    className="p-2 bg-indigo-50 text-indigo-700 rounded-lg border border-indigo-200 hover:bg-indigo-100"
                  >
                    <Eye size={18} />
                  </button>
                </td>
              </tr>
            ))} 
          </tbody>
        </table>
        {bills.length === 0 && !loading && (
          <div className="p-20 text-center text-gray-400 italic">No bills found in the database. Ensure the backend is processing files.</div>
        )}
      </div>

      <DataModal 
        isOpen={modalConfig.isOpen} 
        title={modalConfig.title}
        type={modalConfig.type}
        content={modalConfig.data} 
        onClose={() => setModalConfig({ ...modalConfig, isOpen: false })}
      />
    </div>
  );
}