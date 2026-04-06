/**
 * GraphVisualizer — 3D Canvas-based knowledge graph visualization
 *
 * Force-directed 3D layout with perspective projection on HTML5 Canvas.
 * No external dependencies — pure React + Canvas + math.
 *
 * Features:
 *  - 3D force-directed node layout (spherical initial distribution)
 *  - Perspective projection with depth fog
 *  - Drag to orbit-rotate, scroll to zoom
 *  - Continuous slow auto-rotation when idle
 *  - Color-coded nodes by memory type with glow
 *  - Depth-sorted rendering (painter's algorithm)
 *  - Hover tooltips
 *  - Type filter sidebar
 *  - Arc timeline overlay
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
    GitBranch, Loader2, RefreshCw, ZoomIn, ZoomOut,
    Filter, Info, RotateCcw, Pause, Play,
} from 'lucide-react';
import { getGraphData, type GraphData } from '../services/contextApi';
import { listEntities, type MemoryEntity } from '../services/memoryApi';

/* ────────────────────── edge / relation colours ────────────────────── */
const RELATION_COLORS: Record<string, string> = {
    evolved_from:  '#a78bfa',  // violet
    resolved_by:   '#34d399',  // emerald
    triggered_by:  '#f87171',  // red
    deepens:       '#60a5fa',  // blue
    references:    '#fbbf24',  // amber
    contains:      '#2dd4bf',  // teal
    contrasts:     '#fb923c',  // orange
    // Factual relations
    kin_of:        '#f472b6',  // pink
    companion_of:  '#fb7185',  // rose
    created_by:    '#818cf8',  // indigo
    located_in:    '#a3e635',  // lime
    has_condition: '#f87171',  // red
    symptom_of:    '#fb923c',  // orange
    is_a:          '#06b6d4',  // cyan
    part_of:       '#2dd4bf',  // teal
    owns:          '#fbbf24',  // amber
    knows:         '#60a5fa',  // blue
    works_on:      '#34d399',  // emerald
    related_to:    '#9ca3af',  // gray
    rival_of:      '#ef4444',  // red-500
    enemy_of:      '#dc2626',  // red-600
    formerly:      '#6b7280',  // gray-500
};
const RELATION_FALLBACK = '#888';

/* ────────────────────── node colour palette ────────────────────── */
const TYPE_COLORS: Record<string, string> = {
    lexicon:            '#a78bfa',
    life_event:         '#facc15',
    artifact:           '#60a5fa',
    emotional_pattern:  '#f472b6',
    repair_pattern:     '#34d399',
    repair:             '#34d399',
    pattern:            '#f472b6',
    inside_joke:        '#fbbf24',
    intimate_moment:    '#fb7185',
    unresolved_thread:  '#f87171',
    permission:         '#a3e635',
    narrative:          '#818cf8',
    echo_dream:         '#c084fc',
    ritual:             '#2dd4bf',
    mythology:          '#34d399',
    state_need:         '#fb923c',
    memory_block:       '#06b6d4',
    // Factual entity types (diamonds in render)
    person:             '#f59e0b',  // amber-500
    companion:          '#ec4899',  // pink-500
    place:              '#10b981',  // emerald-500
    object:             '#6366f1',  // indigo-500
    project:            '#8b5cf6',  // violet-500
    condition:          '#ef4444',  // red-500
    symptom:            '#f87171',  // red-400
    concept:            '#06b6d4',  // cyan-500
    group:              '#14b8a6',  // teal-500
    topic:              '#64748b',  // slate-500
};

/* Factual types render as diamonds instead of circles */
const FACTUAL_TYPES = new Set([
    'person', 'companion', 'place', 'object', 'project',
    'condition', 'symptom', 'concept', 'group', 'topic',
]);

/* ────────────────────── simulation types ────────────────────── */
interface SimNode {
    id: string;
    type: string;
    label: string;
    /* world-space */
    x: number; y: number; z: number;
    vx: number; vy: number; vz: number;
    color: string;
    radius: number;
    /* screen-space (filled each frame by project()) */
    sx: number; sy: number; depth: number; scale: number;
}

interface SimEdge {
    source: string;
    target: string;
    relation: string;
    strength: number;
    status: 'active' | 'superseded' | 'historical';
}

/* ────────────────────── math helpers ────────────────────── */
function rotY(x: number, z: number, a: number): [number, number] {
    const c = Math.cos(a), s = Math.sin(a);
    return [x * c + z * s, -x * s + z * c];
}
function rotX(y: number, z: number, a: number): [number, number] {
    const c = Math.cos(a), s = Math.sin(a);
    return [y * c - z * s, y * s + z * c];
}
function hexRgb(hex: string) {
    let h = hex.replace('#', '');
    if (h.length === 3) {
        h = h.split('').map(char => char + char).join('');
    }
    return {
        r: parseInt(h.substring(0, 2), 16) || 0,
        g: parseInt(h.substring(2, 4), 16) || 0,
        b: parseInt(h.substring(4, 6), 16) || 0,
    };
}

/* ================================================================
   Component
   ================================================================ */
interface Props {
    agents?: { id: string; name: string }[];
}

export function GraphVisualizer({ agents }: Props) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const animRef   = useRef(0);

    /* data */
    const [entities, setEntities]           = useState<MemoryEntity[]>([]);
    const [selectedEntity, setSelectedEntity] = useState<MemoryEntity | null>(null);
    const [graphData, setGraphData]         = useState<GraphData | null>(null);
    const [loading, setLoading]             = useState(false);
    const [hoveredNode, setHoveredNode]     = useState<SimNode | null>(null);
    const [hoveredEdge, setHoveredEdge]     = useState<SimEdge | null>(null);
    const [mousePos, setMousePos]           = useState({ x: 0, y: 0 });
    const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
    const [showArcs, setShowArcs]           = useState(false);
    const [showSuperseded, setShowSuperseded] = useState(false);
    const showSupersededRef = useRef(false);
    const [paused, setPaused]               = useState(false);
    const pausedRef = useRef(false);

    /* 3-D camera — refs so the animation loop always sees current values */
    const camDist  = useRef(1100);    // camera distance from origin (bigger = further = smaller graph)
    const azimuth  = useRef(0);       // Y-axis rotation
    const elevation = useRef(0.35);   // X-axis tilt
    const autoRot  = useRef(true);
    const dragging = useRef(false);
    const lastDrag = useRef({ x: 0, y: 0 });

    /* simulation */
    const nodesRef     = useRef<SimNode[]>([]);
    const edgesRef     = useRef<SimEdge[]>([]);
    const nodeMapRef   = useRef<Map<string, SimNode>>(new Map());
    const simAlive     = useRef(true);
    const alpha        = useRef(1);
    const ALPHA_DECAY  = 0.0018;
    const ALPHA_MIN    = 0.0008;
    const selTypesRef  = useRef(selectedTypes);
    useEffect(() => { selTypesRef.current = selectedTypes; }, [selectedTypes]);

    /* ── load entities ── */
    useEffect(() => {
        listEntities().then(data => {
            const list = Array.isArray(data) ? data : [];
            setEntities(list);
            if (list.length > 0) setSelectedEntity(list[0]);
        }).catch(console.error);
    }, []);

    /* ── load graph ── */
    const loadGraph = useCallback(async () => {
        if (!selectedEntity) return;
        setLoading(true);
        try {
            const data = await getGraphData(selectedEntity.id);
            setGraphData(data);
            initSimulation(data);
        } catch (err) { console.error('graph load failed', err); }
        finally { setLoading(false); }
    }, [selectedEntity]);

    useEffect(() => { loadGraph(); }, [loadGraph]);

    /* ─────────────── init simulation ─────────────── */
    const initSimulation = (data: GraphData) => {
        const N = data.nodes.length;
        const spread = Math.max(200, Math.sqrt(N) * 45);

        // Pre-compute edge counts
        const edgeCounts = new Map<string, number>();
        for (const e of data.edges) {
            edgeCounts.set(e.source, (edgeCounts.get(e.source) || 0) + 1);
            edgeCounts.set(e.target, (edgeCounts.get(e.target) || 0) + 1);
        }

        nodesRef.current = data.nodes.map((n, i) => {
            // Fibonacci sphere distribution
            const phi   = Math.acos(1 - 2 * (i + 0.5) / N);
            const theta = Math.PI * (1 + Math.sqrt(5)) * i;
            const r     = spread * (0.6 + Math.random() * 0.4);
            const ec    = edgeCounts.get(n.id) || 0;
            return {
                id: n.id, type: n.type, label: n.label,
                x: r * Math.sin(phi) * Math.cos(theta),
                y: r * Math.sin(phi) * Math.sin(theta),
                z: r * Math.cos(phi),
                vx: 0, vy: 0, vz: 0,
                color: TYPE_COLORS[n.type] || '#ccc',
                radius: 4 + Math.min(ec * 1.4, 14),
                sx: 0, sy: 0, depth: 0, scale: 1,
            };
        });

        edgesRef.current = data.edges.map(e => ({
            source: e.source,
            target: e.target,
            relation: e.relation,
            strength: e.strength,
            status: (e as any).status || 'active',
        }));

        // Build quick-lookup map
        const map = new Map<string, SimNode>();
        for (const n of nodesRef.current) map.set(n.id, n);
        nodeMapRef.current = map;

        const types = new Set(data.nodes.map(n => n.type));
        setSelectedTypes(types);

        alpha.current  = 1;
        autoRot.current = false;        // wait for layout to settle
        simAlive.current = true;
        startLoop();
    };

    /* ─────────────── physics step (3-D) ─────────────── */
    const physicsTick = () => {
        const nodes = nodesRef.current;
        const edges = edgesRef.current;
        const nmap  = nodeMapRef.current;
        if (!nodes.length) return;

        const a = alpha.current;

        /* repulsion — O(n²) but capped at distance 600 */
        const REPULSION = 3000;
        for (let i = 0; i < nodes.length; i++) {
            const ni = nodes[i];
            for (let j = i + 1; j < nodes.length; j++) {
                const nj = nodes[j];
                const dx = ni.x - nj.x;
                const dy = ni.y - nj.y;
                const dz = ni.z - nj.z;
                const d2 = dx * dx + dy * dy + dz * dz;
                if (d2 > 360000) continue;              // 600²
                const dist = Math.sqrt(d2) || 1;
                const f = (REPULSION / (dist * dist)) * a;
                const fx = (dx / dist) * f;
                const fy = (dy / dist) * f;
                const fz = (dz / dist) * f;
                ni.vx += fx; ni.vy += fy; ni.vz += fz;
                nj.vx -= fx; nj.vy -= fy; nj.vz -= fz;
            }
        }

        /* spring attraction along edges */
        const SPRING_LEN   = 160;
        const SPRING_FORCE = 0.012;
        for (const e of edges) {
            const s = nmap.get(e.source);
            const t = nmap.get(e.target);
            if (!s || !t) continue;
            const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
            const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
            const f  = (dist - SPRING_LEN) * SPRING_FORCE * a;
            const fx = (dx / dist) * f;
            const fy = (dy / dist) * f;
            const fz = (dz / dist) * f;
            s.vx += fx; s.vy += fy; s.vz += fz;
            t.vx -= fx; t.vy -= fy; t.vz -= fz;
        }

        /* centering gravity */
        const G = 0.005 * a;
        for (const n of nodes) {
            n.vx -= n.x * G;
            n.vy -= n.y * G;
            n.vz -= n.z * G;
        }

        /* velocity integration + damping */
        const DAMP = 0.78;
        for (const n of nodes) {
            n.vx *= DAMP; n.vy *= DAMP; n.vz *= DAMP;
            n.x += n.vx;  n.y += n.vy;  n.z += n.vz;
        }

        /* cool */
        alpha.current = Math.max(ALPHA_MIN, a - ALPHA_DECAY);
    };

    /* ─────────────── project world → screen ─────────────── */
    const project = () => {
        const cvs = canvasRef.current;
        if (!cvs) return;
        const rect = cvs.getBoundingClientRect();
        const cx = rect.width  / 2;
        const cy = rect.height / 2;
        if (cx === 0 || cy === 0) return;
        const FOCAL = 600;
        const az  = azimuth.current;
        const el  = elevation.current;

        for (const n of nodesRef.current) {
            // rotate Y then X
            const [rx, rz1] = rotY(n.x, n.z, az);
            const [ry, rz2] = rotX(n.y, rz1, el);

            const depth = rz2 + camDist.current;      // camera sits at -camDist looking at origin
            const sc    = Math.max(0.08, FOCAL / Math.max(depth, 1));

            n.sx    = cx + rx * sc;
            n.sy    = cy + ry * sc;
            n.depth = depth;
            n.scale = sc;
        }
    };

    /* ─────────────── render one frame ─────────────── */
    const draw = () => {
        const cvs = canvasRef.current;
        if (!cvs) return;
        const ctx = cvs.getContext('2d');
        if (!ctx) return;

        const nodes = nodesRef.current;
        const edges = edgesRef.current;
        const nmap  = nodeMapRef.current;
        const types = selTypesRef.current;

        // Self-size: read CSS size, set buffer to DPR-scaled resolution
        const rect = cvs.getBoundingClientRect();
        const lw = rect.width;
        const lh = rect.height;
        if (lw === 0 || lh === 0) return;

        const dpr = window.devicePixelRatio || 1;
        const bw = Math.round(lw * dpr);
        const bh = Math.round(lh * dpr);
        if (cvs.width !== bw || cvs.height !== bh) {
            cvs.width  = bw;
            cvs.height = bh;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, lw, lh);

        /* ── edges (colour-coded by relation) ── */
        for (const e of edges) {
            const s = nmap.get(e.source);
            const t = nmap.get(e.target);
            if (!s || !t) continue;
            if (!types.has(s.type) || !types.has(t.type)) continue;

            // Skip superseded/historical edges when hidden
            const isSuperseded = e.status === 'superseded' || e.status === 'historical';
            if (isSuperseded && !showSupersededRef.current) continue;

            const avgD  = (s.depth + t.depth) / 2;
            const dFog  = Math.max(0.06, Math.min(1, 800 / avgD));
            const baseA = (0.12 + e.strength * 0.28) * dFog;
            // Superseded edges are dimmed
            const eA    = isSuperseded ? baseA * 0.35 : baseA;
            const ec    = RELATION_COLORS[e.relation] || RELATION_FALLBACK;
            const { r: er, g: eg, b: eb } = hexRgb(ec);

            ctx.beginPath();
            // Dashed line for superseded edges
            if (isSuperseded) ctx.setLineDash([4, 4]);
            ctx.moveTo(s.sx, s.sy);
            ctx.lineTo(t.sx, t.sy);
            ctx.strokeStyle = `rgba(${er},${eg},${eb},${eA.toFixed(3)})`;
            ctx.lineWidth   = Math.max(0.4, (0.6 + e.strength) * Math.min(s.scale, t.scale));
            ctx.stroke();
            if (isSuperseded) ctx.setLineDash([]);  // reset

            /* edge midpoint label — only when close enough */
            const midScale = Math.min(s.scale, t.scale);
            if (midScale > 0.35 && dFog > 0.25) {
                const mx = (s.sx + t.sx) / 2;
                const my = (s.sy + t.sy) / 2;
                const efs = Math.max(7, Math.round(9 * midScale));
                ctx.font      = `${efs}px sans-serif`;
                ctx.fillStyle = `rgba(${er},${eg},${eb},${(eA * 0.7).toFixed(3)})`;
                ctx.textAlign = 'center';
                const label = isSuperseded
                    ? `⊘ ${e.relation.replace(/_/g, ' ')}`
                    : e.relation.replace(/_/g, ' ');
                ctx.fillText(label, mx, my - 3);
            }
        }

        /* ── nodes: back-to-front ── */
        const sorted = [...nodes].sort((a, b) => b.depth - a.depth);

        for (const n of sorted) {
            if (!types.has(n.type)) continue;
            const r = n.radius * n.scale;
            if (r < 0.4) continue;

            const fog = Math.max(0.15, Math.min(1, 700 / n.depth));
            const { r: cr, g: cg, b: cb } = hexRgb(n.color);

            /* subtle glow — small radius, low opacity for crisp look */
            const glowR = r * 1.8;
            const glow = ctx.createRadialGradient(n.sx, n.sy, r * 0.5, n.sx, n.sy, glowR);
            glow.addColorStop(0, `rgba(${cr},${cg},${cb},${(0.15 * fog).toFixed(3)})`);
            glow.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
            ctx.fillStyle = glow;
            ctx.fillRect(n.sx - glowR, n.sy - glowR, glowR * 2, glowR * 2);

            const isFactual = FACTUAL_TYPES.has(n.type);

            ctx.beginPath();
            if (isFactual) {
                /* diamond shape for factual entities */
                const d = r * 1.25; // slightly larger to match circle area
                ctx.moveTo(n.sx, n.sy - d);
                ctx.lineTo(n.sx + d, n.sy);
                ctx.lineTo(n.sx, n.sy + d);
                ctx.lineTo(n.sx - d, n.sy);
                ctx.closePath();
            } else {
                /* solid node circle for relational-emotional memory */
                ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
            }
            ctx.fillStyle   = `rgba(${cr},${cg},${cb},${(0.85 * fog).toFixed(3)})`;
            ctx.fill();
            ctx.strokeStyle  = `rgba(${cr},${cg},${cb},${(0.95 * fog).toFixed(3)})`;
            ctx.lineWidth    = Math.max(0.5, 1.5 * n.scale);
            ctx.stroke();

            /* label — scales with perspective, hides when too small */
            const fs = Math.round(11 * n.scale);
            if (fs >= 5 && fog > 0.2) {
                ctx.font      = `${fs}px sans-serif`;
                ctx.fillStyle = `rgba(${cr},${cg},${cb},${(fog * 0.9).toFixed(3)})`;
                ctx.textAlign = 'center';
                const lbl = n.label.length > 24 ? n.label.slice(0, 23) + '…' : n.label;
                ctx.fillText(lbl, n.sx, n.sy + r + fs + 1);
            }
        }
    };

    /* ─────────────── animation loop ─────────────── */
    const startLoop = () => {
        const tick = () => {
            /* physics while hot */
            if (alpha.current > ALPHA_MIN) {
                physicsTick();
            } else if (!autoRot.current) {
                autoRot.current = true;       // layout settled → begin auto-rotate
            }

            /* gentle auto-rotation (respects pause) */
            if (autoRot.current && !dragging.current && !pausedRef.current) {
                azimuth.current += 0.003;
            }

            project();
            draw();

            if (simAlive.current) {
                animRef.current = requestAnimationFrame(tick);
            }
        };
        tick();
    };

    /* cleanup */
    useEffect(() => () => {
        simAlive.current = false;
        cancelAnimationFrame(animRef.current);
    }, []);

    /* ── wheel → zoom ── */
    const onWheel = useCallback((e: WheelEvent) => {
        e.preventDefault();
        // scroll up (deltaY < 0) = zoom in = move camera closer
        const factor = e.deltaY > 0 ? 1.08 : 0.92;
        camDist.current = Math.max(300, Math.min(3000, camDist.current * factor));
    }, []);

    useEffect(() => {
        const cvs = canvasRef.current;
        if (!cvs) return;
        cvs.addEventListener('wheel', onWheel, { passive: false });
        return () => cvs.removeEventListener('wheel', onWheel);
    }, [onWheel]);

    /* ── mouse: hover + orbit drag ── */
    const onMouseMove = (e: React.MouseEvent) => {
        const cvs = canvasRef.current;
        if (!cvs) return;
        const rect = cvs.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        setMousePos({ x: mx, y: my });

        if (dragging.current) {
            const dx = e.clientX - lastDrag.current.x;
            const dy = e.clientY - lastDrag.current.y;
            azimuth.current  += dx * 0.005;
            elevation.current = Math.max(-1.3, Math.min(1.3, elevation.current + dy * 0.005));
            lastDrag.current  = { x: e.clientX, y: e.clientY };
            return;
        }

        /* hit-test nodes — prefer frontmost */
        let hit: SimNode | null = null;
        for (const n of nodesRef.current) {
            if (!selTypesRef.current.has(n.type)) continue;
            const dx = n.sx - mx, dy = n.sy - my;
            const hr = n.radius * n.scale + 6;
            if (dx * dx + dy * dy < hr * hr) {
                if (!hit || n.depth < hit.depth) hit = n;
            }
        }
        setHoveredNode(hit);

        /* hit-test edges — point-to-segment distance */
        if (!hit) {
            let hitEdge: SimEdge | null = null;
            let bestDist = 8; // max pixel distance to count as hover
            for (const e of edgesRef.current) {
                const s = nodeMapRef.current.get(e.source);
                const t = nodeMapRef.current.get(e.target);
                if (!s || !t) continue;
                const edx = t.sx - s.sx, edy = t.sy - s.sy;
                const len2 = edx * edx + edy * edy;
                if (len2 < 1) continue;
                const param = Math.max(0, Math.min(1, ((mx - s.sx) * edx + (my - s.sy) * edy) / len2));
                const px = s.sx + param * edx - mx;
                const py = s.sy + param * edy - my;
                const d = Math.sqrt(px * px + py * py);
                if (d < bestDist) { bestDist = d; hitEdge = e; }
            }
            setHoveredEdge(hitEdge);
        } else {
            setHoveredEdge(null);
        }
    };

    const onDown = (e: React.MouseEvent) => {
        if (e.button === 0) {
            dragging.current = true;
            autoRot.current  = false;
            lastDrag.current = { x: e.clientX, y: e.clientY };
        }
    };

    const onUp = () => {
        if (dragging.current) {
            dragging.current = false;
            if (!pausedRef.current) {
                setTimeout(() => { if (!dragging.current) autoRot.current = true; }, 1500);
            }
        }
    };

    const togglePause = () => {
        setPaused(p => {
            const next = !p;
            pausedRef.current = next;
            if (next) {
                autoRot.current = false;
            } else {
                autoRot.current = true;
            }
            return next;
        });
    };

    /* toggle type filter */
    const toggleType = (t: string) =>
        setSelectedTypes(prev => {
            const s = new Set(prev);
            s.has(t) ? s.delete(t) : s.add(t);
            return s;
        });

    /* ================================================================
       JSX
       ================================================================ */
    return (
        <div style={{
            display: 'flex', flexDirection: 'column', height: '100%',
            background: 'var(--bg-primary,#0a0a0f)', color: '#e0e0e0',
        }}>
            {/* ── header ── */}
            <div style={{
                padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,.08)',
                display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0,
            }}>
                <GitBranch size={20} style={{ color: '#34d399' }} />
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Knowledge Graph · 3D</h2>

                <select
                    value={selectedEntity?.id || ''}
                    onChange={e => {
                        const ent = entities.find(en => en.id === e.target.value);
                        if (ent) setSelectedEntity(ent);
                    }}
                    style={{
                        background: 'rgba(255,255,255,.06)', border: '1px solid rgba(255,255,255,.1)',
                        color: '#e0e0e0', padding: '6px 12px', borderRadius: 6, fontSize: 13,
                    }}
                >
                    {entities.map(e => <option key={e.id} value={e.id}>{e.name || e.id}</option>)}
                </select>

                <div style={{ flex: 1 }} />

                {graphData && (
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'rgba(255,255,255,.5)' }}>
                        <span>{graphData.stats.total_nodes} nodes</span>
                        <span>{graphData.stats.total_edges} edges</span>
                        <span>{graphData.stats.total_arcs} arcs</span>
                    </div>
                )}

                <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={togglePause}
                        style={{ ...btnStyle, background: paused ? 'rgba(167,139,250,.18)' : btnStyle.background }}
                        title={paused ? 'Resume rotation' : 'Pause rotation'}>
                        {paused ? <Play size={14} /> : <Pause size={14} />}
                    </button>
                    <button onClick={() => { camDist.current = Math.max(300, camDist.current * 0.82); }}
                        style={btnStyle} title="Zoom in"><ZoomIn size={14} /></button>
                    <button onClick={() => { camDist.current = Math.min(3000, camDist.current * 1.18); }}
                        style={btnStyle} title="Zoom out"><ZoomOut size={14} /></button>
                    <button onClick={() => { camDist.current = 1100; azimuth.current = 0; elevation.current = 0.35; autoRot.current = true; setPaused(false); pausedRef.current = false; }}
                        style={btnStyle} title="Reset view"><RotateCcw size={14} /></button>
                </div>

                <button onClick={loadGraph} disabled={loading}
                    style={{ ...btnStyle, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                    Refresh
                </button>
            </div>

            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                {/* ── sidebar ── */}
                <div style={{
                    width: 180, borderRight: '1px solid rgba(255,255,255,.06)',
                    padding: 12, overflow: 'auto', flexShrink: 0,
                }}>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,.4)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Filter size={12} /> NODE TYPES
                    </div>
                    {graphData?.stats.node_types.map(type => (
                        <label key={type} style={{
                            display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0',
                            fontSize: 12, cursor: 'pointer', opacity: selectedTypes.has(type) ? 1 : 0.4,
                        }}>
                            <input type="checkbox" checked={selectedTypes.has(type)}
                                onChange={() => toggleType(type)}
                                style={{ accentColor: TYPE_COLORS[type] || '#888' }} />
                            {FACTUAL_TYPES.has(type) ? (
                                /* diamond swatch for factual types */
                                <div style={{
                                    width: 10, height: 10,
                                    background: TYPE_COLORS[type] || '#888',
                                    transform: 'rotate(45deg)',
                                    borderRadius: 1, flexShrink: 0,
                                }} />
                            ) : (
                                /* circle swatch for relational-emotional types */
                                <div style={{ width: 8, height: 8, borderRadius: '50%', background: TYPE_COLORS[type] || '#888', flexShrink: 0 }} />
                            )}
                            <span>{type.replace(/_/g, ' ')}</span>
                        </label>
                    ))}

                    {graphData && graphData.stats.relation_types.length > 0 && (
                        <>
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,.4)', marginTop: 16, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                                <Info size={12} /> RELATIONS
                            </div>
                            {graphData.stats.relation_types.map(rel => (
                                <div key={rel} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'rgba(255,255,255,.5)', padding: '2px 0' }}>
                                    <div style={{ width: 16, height: 2, borderRadius: 1, background: RELATION_COLORS[rel] || RELATION_FALLBACK, flexShrink: 0 }} />
                                    {rel.replace(/_/g, ' ')}
                                </div>
                            ))}
                        </>
                    )}

                    {graphData && graphData.arcs.length > 0 && (
                        <>
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,.4)', marginTop: 16, marginBottom: 8 }}>
                                NARRATIVE ARCS ({graphData.arcs.length})
                            </div>
                            <button onClick={() => setShowArcs(!showArcs)}
                                style={{
                                    background: showArcs ? 'rgba(167,139,250,.15)' : 'rgba(255,255,255,.06)',
                                    border: '1px solid rgba(255,255,255,.1)',
                                    color: showArcs ? '#a78bfa' : '#aaa',
                                    padding: '4px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11, width: '100%',
                                }}>
                                {showArcs ? 'Hide Arcs' : 'Show Arcs'}
                            </button>
                        </>
                    )}

                    <div style={{ marginTop: 16 }}>
                        <button onClick={() => { setShowSuperseded(v => { const next = !v; showSupersededRef.current = next; return next; }); }}
                            style={{
                                background: showSuperseded ? 'rgba(239,68,68,.15)' : 'rgba(255,255,255,.06)',
                                border: '1px solid rgba(255,255,255,.1)',
                                color: showSuperseded ? '#ef4444' : '#aaa',
                                padding: '4px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11, width: '100%',
                            }}>
                            {showSuperseded ? 'Hide Superseded' : 'Show Superseded'}
                        </button>
                    </div>

                    <div style={{ marginTop: 24, fontSize: 10, color: 'rgba(255,255,255,.25)', lineHeight: 1.6 }}>
                        <div>🖱️ Drag to rotate</div>
                        <div>🔄 Scroll to zoom</div>
                        <div>Auto-rotates when idle</div>
                    </div>
                </div>

                {/* ── canvas ── */}
                <div style={{ flex: 1, position: 'relative' }}>
                    {loading ? (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                            <Loader2 size={32} className="spin" style={{ color: '#34d399' }} />
                        </div>
                    ) : graphData && graphData.nodes.length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#666' }}>
                            <GitBranch size={48} style={{ marginBottom: 16, opacity: 0.3 }} />
                            <p style={{ fontSize: 14 }}>No graph edges found</p>
                            <p style={{ fontSize: 12, opacity: 0.5 }}>Run a harvest to generate knowledge graph connections</p>
                        </div>
                    ) : (
                        <canvas ref={canvasRef}
                            onMouseMove={onMouseMove}
                            onMouseDown={onDown}
                            onMouseUp={onUp}
                            onMouseLeave={onUp}
                            style={{ width: '100%', height: '100%', cursor: dragging.current ? 'grabbing' : hoveredNode ? 'pointer' : 'grab' }}
                        />
                    )}

                    {/* node tooltip */}
                    {hoveredNode && (
                        <div style={{
                            position: 'absolute', left: mousePos.x + 14, top: mousePos.y - 10,
                            background: 'rgba(10,10,15,.95)',
                            border: `1px solid ${hoveredNode.color}40`,
                            borderRadius: 8, padding: '8px 12px',
                            pointerEvents: 'none', zIndex: 10, maxWidth: 280,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                {FACTUAL_TYPES.has(hoveredNode.type) ? (
                                    <div style={{ width: 8, height: 8, background: hoveredNode.color, transform: 'rotate(45deg)', borderRadius: 1 }} />
                                ) : (
                                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: hoveredNode.color }} />
                                )}
                                <span style={{ fontSize: 12, fontWeight: 600, color: hoveredNode.color }}>
                                    {hoveredNode.type.replace(/_/g, ' ')}
                                </span>
                            </div>
                            <div style={{ fontSize: 12, color: '#ddd', lineHeight: 1.4 }}>{hoveredNode.label}</div>
                        </div>
                    )}

                    {/* edge tooltip */}
                    {hoveredEdge && !hoveredNode && (() => {
                        const ec = RELATION_COLORS[hoveredEdge.relation] || RELATION_FALLBACK;
                        const srcNode = nodesRef.current.find(n => n.id === hoveredEdge.source);
                        const tgtNode = nodesRef.current.find(n => n.id === hoveredEdge.target);
                        return (
                            <div style={{
                                position: 'absolute', left: mousePos.x + 14, top: mousePos.y - 10,
                                background: 'rgba(10,10,15,.95)',
                                border: `1px solid ${ec}40`,
                                borderRadius: 8, padding: '8px 12px',
                                pointerEvents: 'none', zIndex: 10, maxWidth: 300,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                                    <div style={{ width: 16, height: 3, borderRadius: 2, background: ec }} />
                                    <span style={{ fontSize: 12, fontWeight: 600, color: ec }}>
                                        {hoveredEdge.relation.replace(/_/g, ' ')}
                                    </span>
                                    <span style={{ fontSize: 10, color: 'rgba(255,255,255,.4)' }}>
                                        strength {hoveredEdge.strength.toFixed(1)}
                                    </span>
                                    {hoveredEdge.status !== 'active' && (
                                        <span style={{ fontSize: 9, color: '#ef4444', background: 'rgba(239,68,68,.12)', padding: '1px 5px', borderRadius: 3 }}>
                                            {hoveredEdge.status}
                                        </span>
                                    )}
                                </div>
                                <div style={{ fontSize: 11, color: '#bbb', lineHeight: 1.4 }}>
                                    {srcNode?.label || hoveredEdge.source}
                                    <span style={{ color: '#666', margin: '0 6px' }}>→</span>
                                    {tgtNode?.label || hoveredEdge.target}
                                </div>
                            </div>
                        );
                    })()}

                    {/* arc timeline */}
                    {showArcs && graphData && graphData.arcs.length > 0 && (
                        <div style={{
                            position: 'absolute', bottom: 0, left: 0, right: 0,
                            background: 'rgba(10,10,15,.9)',
                            borderTop: '1px solid rgba(255,255,255,.08)',
                            maxHeight: 200, overflow: 'auto', padding: 12,
                        }}>
                            <div style={{ fontSize: 11, color: '#a78bfa', marginBottom: 8, fontWeight: 600 }}>Narrative Arcs</div>
                            {graphData.arcs.map((arc: any) => (
                                <div key={arc.id} style={{
                                    background: 'rgba(255,255,255,.03)', borderRadius: 6, padding: '8px 12px', marginBottom: 6,
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, color: '#e0e0e0' }}>{arc.title}</span>
                                        <span style={{
                                            fontSize: 10, padding: '1px 6px', borderRadius: 3,
                                            background: arc.status === 'resolved' ? 'rgba(52,211,153,.15)' : 'rgba(251,191,36,.15)',
                                            color: arc.status === 'resolved' ? '#34d399' : '#fbbf24',
                                        }}>{arc.status}</span>
                                    </div>
                                    {arc.events && (
                                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                            {arc.events.map((ev: any, i: number) => (
                                                <span key={i} style={{
                                                    fontSize: 10, padding: '2px 6px',
                                                    background: 'rgba(255,255,255,.05)', borderRadius: 3, color: '#aaa',
                                                }}>{ev.event_type}: {ev.narrative?.slice(0, 40) || '...'}</span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* shared button style */
const btnStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,.06)',
    border: '1px solid rgba(255,255,255,.1)',
    color: '#e0e0e0',
    padding: '4px 6px',
    borderRadius: 4,
    cursor: 'pointer',
};
