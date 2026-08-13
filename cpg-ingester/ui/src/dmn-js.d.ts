declare module 'dmn-js' {
  interface DmnViewerOptions {
    container?: HTMLElement;
  }

  interface DmnView {
    type: string;
    element?: unknown;
  }

  export default class DmnViewer {
    constructor(options?: DmnViewerOptions);
    importXML(xml: string): Promise<{ warnings: string[] }>;
    getViews(): DmnView[];
    open(view: DmnView): void;
    destroy(): void;
  }
}
