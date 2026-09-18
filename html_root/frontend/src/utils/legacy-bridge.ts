export interface LegacyApp {
  __setCurrentSection?: (id: string) => void;
  __openSettings?: (...args: unknown[]) => void;
  __toggleMobileMenu?: () => void;
}

export interface LegacyAgent {
  toggleSidebar?: () => void;
  openSidebarMobile?: () => void;
  closeSidebarMobile?: () => void;
  toggleFeaturesExamples?: () => void;
  clearChat?: () => void;
  openTemplatesModal?: () => void;
  clearAttachedImage?: () => void;
  execute?: () => void;
}

declare global {
  interface Window {
    App?: LegacyApp;
    Agent?: LegacyAgent;
    ImageEditor?: {
      openEditor?: (id: string, scope: string) => void;
    };
    renderMathInElement?: (el: HTMLElement, opts?: unknown) => void;
    toggleAuthModal?: (show: boolean) => void;
    showSection?: (id: string) => void;
    openSettings?: (...args: unknown[]) => void;
    toggleMobileMenu?: () => void;
  }
}

export function getLegacyApp(): LegacyApp {
  window.App = window.App || {};
  return window.App;
}

export function getLegacyAgent(): LegacyAgent | undefined {
  return window.Agent;
}

