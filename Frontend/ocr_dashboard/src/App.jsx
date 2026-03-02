import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import DataModal from './components/DataModal';

function App() {
  const [modalOpen, setModalOpen] = useState(false);
  const [modalContent, setModalContent] = useState({});

  const handleOpenModal = (content) => {
    setModalContent(content);
    setModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#f4f7fe]">
      {/* Updated Navbar to match the screenshot */}
      <nav className="bg-white px-8 py-3 shadow-sm flex justify-between items-center border-b border-gray-100">
        {/* Left Side: Empty or Simple Menu Icon as seen in screenshot */}
        <div className="flex items-center">
          <button className="text-gray-600 hover:bg-gray-100 p-2 rounded-lg">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
          </button>
        </div>

        {/* Right Side: User Profile Section */}
        <div className="flex items-center gap-3">
          <div className="text-right mr-2">
            <p className="text-sm font-bold text-slate-800 leading-none">Company User</p>
            <p className="text-[11px] text-slate-500 font-medium">compuser@technossus.com</p>
            <p className="text-[11px] text-slate-400">companyuser</p>
          </div>
          
          {/* Dummy Profile Photo */}
          <div className="relative">
            <img 
              src="https://ui-avatars.com/api/?name=Company+User&background=e2e8f0&color=475569" 
              alt="User Profile" 
              className="w-10 h-10 rounded-full border-2 border-gray-200 object-cover shadow-sm"
            />
            {/* Green Online Status Dot */}
            <span className="absolute bottom-0 right-0 block h-2.5 w-2.5 rounded-full bg-green-500 ring-2 ring-white"></span>
          </div>
        </div>
      </nav>
      
      {/* Main Content Area */}
      <main className="py-4">
        <Dashboard onOpenModal={handleOpenModal} />
      </main>
      
      <DataModal 
        isOpen={modalOpen} 
        content={modalContent} 
        onClose={() => setModalOpen(false)} 
      />

      {/* Footer from screenshot */}
      <footer className="fixed bottom-0 w-full bg-transparent p-4 text-right">
        <p className="text-[10px] text-gray-400">
          ©2025 Technossus, Digital Solutions Studio. All rights reserved.
        </p>
      </footer>
    </div>
  );
}

export default App;