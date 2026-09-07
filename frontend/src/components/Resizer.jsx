import React, { useRef } from "react";

/**
 * Dependency-free drag handle. Fires onDrag(deltaPixels) on every pointer
 * move while dragging; the parent owns the actual size state and decides
 * how to clamp it. Uses pointer capture so fast drags that leave the
 * handle's bounding box don't drop the interaction.
 */
export function Resizer({ onDrag, orientation = "vertical", title }) {
  const draggingRef = useRef(false);
  const lastPosRef = useRef(0);

  const posFromEvent = (e) => (orientation === "vertical" ? e.clientX : e.clientY);

  const handlePointerDown = (e) => {
    draggingRef.current = true;
    lastPosRef.current = posFromEvent(e);
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.style.cursor = orientation === "vertical" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
  };

  const handlePointerMove = (e) => {
    if (!draggingRef.current) return;
    const pos = posFromEvent(e);
    const delta = pos - lastPosRef.current;
    lastPosRef.current = pos;
    if (delta !== 0) onDrag(delta);
  };

  const stop = () => {
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };

  return (
    <div
      className={`resizer resizer-${orientation}`}
      title={title}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={stop}
      onPointerCancel={stop}
    />
  );
}
