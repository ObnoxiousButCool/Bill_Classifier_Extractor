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
    <div className="min-h-screen bg-gray-100">
      <nav className="bg-white p-4 shadow-sm">
        <h1 className="text-xl font-black text-blue-600">BILL SCANNER</h1>
      </nav>
      
      <Dashboard onOpenModal={handleOpenModal} />
      
      <DataModal 
        isOpen={modalOpen} 
        content={modalContent} 
        onClose={() => setModalOpen(false)} 
      />
    </div>
  );
}

export default App;