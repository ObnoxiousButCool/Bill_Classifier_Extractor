import React, { useState, useEffect } from 'react';
import { FileJson, Eye, RefreshCw, ClipboardList } from 'lucide-react';
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
      hour: '2-digit', minute: '2-digit',
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
    <div className="p-8 bg-[#f4f7fe] min-h-screen font-sans">
      <div className="max-w-7xl mx-auto mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-semibold text-[#2d3748]">Document Processing</h1>
        </div>
        <button 
          onClick={fetchData} 
          className="flex items-center gap-2 px-5 py-2.5 bg-white border border-gray-200 rounded-lg shadow-sm hover:bg-gray-50 text-sm font-medium text-gray-700 transition-all"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Refresh Data
        </button>
      </div>

      <div className="max-w-7xl mx-auto bg-white shadow-sm rounded-none overflow-hidden border border-gray-100">
        <table className="w-full text-left border-collapse">
          {/* --- Table Header Section --- */}
          <thead className="bg-[#434d93] text-white">
            <tr>
              {/* Increased font to text-sm (14px) and added text-center to all */}
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">Document ID</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">Created At</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">Type of bill</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">Extracted JSON</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">NetSuite JSON</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center border-r border-[#545da7]">Tally XML</th>
              <th className="p-5 text-sm font-bold uppercase tracking-wider text-center">View</th>
            </tr>
          </thead>

          {/* --- Table Body Section --- */}
          <tbody className="divide-y divide-gray-200 bg-white">
            {bills.map((bill) => (
              <tr key={bill.bill_id} className="hover:bg-slate-50 transition-colors">
                {/* Centered all <td> content to match the new headers */}
                <td className="p-5 text-center font-mono text-xs text-slate-500">
                  {bill.bill_id.slice(0, 8)}...
                </td>
                
                <td className="p-5 text-center text-[13px] text-slate-600 font-medium">
                  {formatDateTime(bill.created_at)}
                </td>
                
                <td className="p-5 text-center">
                  <div className="flex flex-col items-center">
                    <span className="text-sm font-semibold text-slate-700">{bill.bill_type}</span>
                    <span className="text-[11px] text-slate-400 italic">{bill.bill_subtype || 'N/A'}</span>
                  </div>
                </td>
                
                {/* Action buttons remain centered as per previous code */}
                <td className="p-5 text-center">
                  <button 
                    onClick={() => openModal(bill.extracted_json, 'Extracted Data', 'json')}
                    className="p-2.5 bg-[#eef2ff] text-[#4f46e5] rounded-lg hover:bg-blue-100 transition-colors"
                  >
                    <FileJson size={20} />
                  </button>
                </td>

                <td className="p-5 text-center">
                  <button 
                    onClick={() => openModal(bill.netsuite_json, 'NetSuite Payload', 'json')}
                    className="p-2.5 bg-[#f5f3ff] text-[#7c3aed] rounded-lg hover:bg-indigo-100 transition-colors"
                  >
                    <FileJson size={20} />
                  </button>
                </td>

                <td className="p-5 text-center">
                  <button 
                    onClick={() => openModal(bill.tally_xml, 'Tally XML Export', 'xml')}
                    className="p-2.5 bg-[#ecfdf5] text-[#10b981] rounded-lg hover:bg-emerald-100 transition-colors"
                  >
                    <ClipboardList size={20} />
                  </button>
                </td>

                <td className="p-5 text-center">
                  <button 
                    onClick={() => {
                      const localUrl = `http://localhost:9000/${bill.bill_id}.jpg`;
                      openModal(localUrl, 'Original Bill', 'image');
                    }}
                    className="p-2 text-[#434d93] hover:scale-110 transition-transform"
                  >
                    <Eye size={22} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        
        {/* Pagination Footer Placeholder to match UI screenshot */}
        <div className="p-4 border-t border-gray-100 flex justify-end items-center gap-4 bg-white text-sm text-gray-500">
           <span>Items per page: 10</span>
           <span>1 - {bills.length} of {bills.length}</span>
        </div>

        {bills.length === 0 && !loading && (
          <div className="p-20 text-center text-gray-400 italic bg-white">No documents found.</div>
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