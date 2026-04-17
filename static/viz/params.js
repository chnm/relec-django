// Stub for Hugo @params import
// This was used by Hugo to pass parameters to visualizations
// For Django, each visualization wrapper sets window.__currentVizParams
// before importing the viz module

const params = window.__currentVizParams || { id: '' };

export default params;
export const id = params.id;
