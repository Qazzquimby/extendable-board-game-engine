import '@testing-library/jest-dom';

// jsdom does not implement scrollIntoView — polyfill for components that call it
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
