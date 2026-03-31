import { useRef, useState, useCallback } from 'react';
import { useTabStore } from '../../store/useTabStore';

export function TabBar() {
  const tabs        = useTabStore(s => s.tabs);
  const activeTabId = useTabStore(s => s.activeTabId);
  const { addTab, removeTab, renameTab, setActiveTab } = useTabStore();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName]   = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const startRename = useCallback((tabId: string, name: string) => {
    setEditingId(tabId);
    setEditName(name);
    setTimeout(() => inputRef.current?.select(), 30);
  }, []);

  const commitRename = useCallback(() => {
    if (editingId && editName.trim()) renameTab(editingId, editName.trim());
    setEditingId(null);
  }, [editingId, editName, renameTab]);

  return (
    <div className="tab-bar">
      <div className="tab-list">
        {tabs.map(tab => (
          <div
            key={tab.id}
            className={`tab-item${tab.id === activeTabId ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            onDoubleClick={() => startRename(tab.id, tab.name)}
          >
            {editingId === tab.id ? (
              <input
                ref={inputRef}
                className="tab-rename-input"
                value={editName}
                onChange={e => setEditName(e.target.value)}
                onBlur={commitRename}
                onKeyDown={e => {
                  if (e.key === 'Enter') commitRename();
                  if (e.key === 'Escape') setEditingId(null);
                }}
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <span className="tab-name">{tab.name}</span>
            )}
            {tabs.length > 1 && (
              <button
                className="tab-close"
                onClick={e => { e.stopPropagation(); removeTab(tab.id); }}
                title="Close tab"
              >
                ×
              </button>
            )}
          </div>
        ))}

        <button className="tab-add" onClick={addTab} title="New tab">+</button>
      </div>
    </div>
  );
}
