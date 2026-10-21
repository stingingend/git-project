"use client";

import { useEffect, useRef, useState } from "react";
import type { DependencyGraph } from "../lib/types";
import { graphFrame, transitionFrame, type GraphFrame } from "../lib/graph-motion";

export function useGraphMotion(graph: DependencyGraph | null) {
  const [frame, setFrame] = useState<GraphFrame | null>(null);
  const [settledFor, setSettledFor] = useState<DependencyGraph | null>(null);
  const current = useRef<GraphFrame | null>(null);
  useEffect(() => {
    if (!graph?.ready) return;
    const target = graphFrame(graph);
    const from = current.current;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let animation = 0;
    const update = (next: GraphFrame) => { current.current = next; setFrame(next); };
    const finish = () => { cancelAnimationFrame(animation); update(target); setSettledFor(graph); };
    if (media.matches) finish();
    else {
      const started = performance.now();
      update(transitionFrame(from, target, 0));
      const tick = (now: number) => {
        const elapsed = Math.min(1, (now - started) / 420);
        update(transitionFrame(from, target, 1 - (1 - elapsed) ** 3));
        if (elapsed < 1) animation = requestAnimationFrame(tick);
        else setSettledFor(graph);
      };
      animation = requestAnimationFrame(tick);
    }
    const changed = () => { if (media.matches) finish(); };
    media.addEventListener("change", changed);
    return () => { cancelAnimationFrame(animation); media.removeEventListener("change", changed); };
  }, [graph]);
  return { frame, settled: settledFor === graph };
}
