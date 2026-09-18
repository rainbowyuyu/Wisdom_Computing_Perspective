let tutorModule: Promise<any> | null = null;
export function getTutor() {
  if (!tutorModule) {
    const url = "/static/js/step-tutor.js?v=20260918-progress-1";
    tutorModule = import(/* @vite-ignore */ url).catch(error => { tutorModule = null; throw error; });
  }
  return tutorModule;
}
(window as any).loadStepTutor = getTutor;
