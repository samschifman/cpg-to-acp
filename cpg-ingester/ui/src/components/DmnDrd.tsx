import { useEffect, useRef } from 'react';
import DmnViewer from 'dmn-js';

import 'dmn-js/dist/assets/dmn-js-shared.css';
import 'dmn-js/dist/assets/dmn-js-drd.css';
import 'dmn-js/dist/assets/dmn-font/css/dmn-embedded.css';

interface DmnDrdProps {
  xml: string;
}

export function DmnDrd({ xml }: DmnDrdProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<InstanceType<typeof DmnViewer> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const viewer = new DmnViewer({
      container: containerRef.current,
    });
    viewerRef.current = viewer;

    return () => {
      viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!viewerRef.current || !xml) return;

    viewerRef.current.importXML(xml).then(() => {
      const views = viewerRef.current!.getViews();
      const drdView = views.find((v) => v.type === 'drd');
      if (drdView) {
        viewerRef.current!.open(drdView);
      }
    }).catch((err: Error) => {
      console.error('DMN DRD import failed:', err);
    });
  }, [xml]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', minHeight: 200, overflow: 'auto' }}
    />
  );
}
