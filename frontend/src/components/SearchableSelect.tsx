import React, { useState, useRef, useEffect, useMemo } from 'react';

interface SearchableSelectProps {
  value: string;
  options: string[];
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  /** Format option text for display (e.g. strip prefixes) */
  formatLabel?: (option: string) => string;
  /** Group options by a key derived from the option string */
  groupBy?: (option: string) => string;
}

/**
 * A searchable select/combobox component.
 * Supports filtering, keyboard navigation, and optional grouping.
 */
export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  value,
  options,
  onChange,
  placeholder = 'Search…',
  className = '',
  formatLabel,
  groupBy,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [highlightIdx, setHighlightIdx] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const label = formatLabel || ((o: string) => o);

  // Filter options by search query
  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.toLowerCase();
    return options.filter(o => o.toLowerCase().includes(q) || label(o).toLowerCase().includes(q));
  }, [options, search, label]);

  // Group filtered options if groupBy is provided
  const grouped = useMemo(() => {
    if (!groupBy) return null;
    const groups: Record<string, string[]> = {};
    for (const o of filtered) {
      const key = groupBy(o);
      (groups[key] ??= []).push(o);
    }
    // Sort group keys
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered, groupBy]);

  // Flat list for keyboard navigation
  const flatList = useMemo(() => {
    if (!grouped) return filtered;
    return grouped.flatMap(([, items]) => items);
  }, [grouped, filtered]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Scroll highlighted item into view
  useEffect(() => {
    if (!isOpen || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${highlightIdx}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlightIdx, isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setIsOpen(true);
        e.preventDefault();
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightIdx(i => Math.min(i + 1, flatList.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightIdx(i => Math.max(i - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (flatList[highlightIdx]) {
          onChange(flatList[highlightIdx]);
          setIsOpen(false);
          setSearch('');
        }
        break;
      case 'Escape':
        setIsOpen(false);
        setSearch('');
        break;
    }
  };

  const openDropdown = () => {
    setIsOpen(true);
    setSearch('');
    setHighlightIdx(0);
    // Focus input on next tick
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const selectOption = (opt: string) => {
    onChange(opt);
    setIsOpen(false);
    setSearch('');
  };

  // Render flat or grouped list
  let globalIdx = 0;
  const renderOptions = () => {
    if (flatList.length === 0) {
      return <div className="px-3 py-2 text-gray-500 text-sm">No matches</div>;
    }

    if (grouped) {
      return grouped.map(([group, items]) => (
        <div key={group}>
          <div className="px-3 py-1.5 text-[10px] font-bold text-gray-500 uppercase tracking-wider bg-nexus-900/80 sticky top-0">
            {group}
          </div>
          {items.map(opt => {
            const idx = globalIdx++;
            return (
              <div
                key={opt}
                data-idx={idx}
                className={`px-3 py-1.5 text-sm cursor-pointer truncate ${
                  idx === highlightIdx ? 'bg-nexus-accent/20 text-white' : 'text-gray-300 hover:bg-white/5'
                } ${opt === value ? 'font-semibold text-nexus-accent' : ''}`}
                onMouseEnter={() => setHighlightIdx(idx)}
                onMouseDown={(e) => { e.preventDefault(); selectOption(opt); }}
              >
                {label(opt)}
              </div>
            );
          })}
        </div>
      ));
    }

    return flatList.map((opt, idx) => (
      <div
        key={opt}
        data-idx={idx}
        className={`px-3 py-1.5 text-sm cursor-pointer truncate ${
          idx === highlightIdx ? 'bg-nexus-accent/20 text-white' : 'text-gray-300 hover:bg-white/5'
        } ${opt === value ? 'font-semibold text-nexus-accent' : ''}`}
        onMouseEnter={() => setHighlightIdx(idx)}
        onMouseDown={(e) => { e.preventDefault(); selectOption(opt); }}
      >
        {label(opt)}
      </div>
    ));
  };

  // Reset globalIdx before render
  globalIdx = 0;

  return (
    <div ref={containerRef} className={`relative ${className}`} onKeyDown={handleKeyDown}>
      {/* Trigger button — shows current value */}
      <button
        type="button"
        onClick={openDropdown}
        className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2.5 text-sm text-left text-white focus:border-nexus-accent outline-none truncate"
      >
        {value ? label(value) : <span className="text-gray-500">{placeholder}</span>}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-nexus-800 border border-white/10 rounded-lg shadow-xl overflow-hidden"
          style={{ minWidth: '100%', maxWidth: '400px' }}
        >
          {/* Search input */}
          <div className="p-2 border-b border-white/5">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => { setSearch(e.target.value); setHighlightIdx(0); }}
              placeholder={placeholder}
              className="w-full bg-nexus-900 border border-white/10 rounded px-2.5 py-1.5 text-sm text-white placeholder-gray-500 focus:border-nexus-accent outline-none"
            />
          </div>
          {/* Options list */}
          <div ref={listRef} className="max-h-60 overflow-y-auto">
            {renderOptions()}
          </div>
          {/* Count footer */}
          <div className="px-3 py-1 text-[10px] text-gray-600 border-t border-white/5">
            {flatList.length} of {options.length} models
          </div>
        </div>
      )}
    </div>
  );
};
