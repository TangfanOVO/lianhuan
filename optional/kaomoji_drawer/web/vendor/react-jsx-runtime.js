/* esm.sh - react@19.2.8/jsx-runtime */
var p=Object.create;var j=Object.defineProperty;var v=Object.getOwnPropertyDescriptor;var a=Object.getOwnPropertyNames;var k=Object.getPrototypeOf,T=Object.prototype.hasOwnProperty;var n=(t,r)=>()=>{try{return r||t((r={exports:{}}).exports,r),r.exports}catch(e){throw r=0,e}};var f=(t,r,e,o)=>{if(r&&typeof r=="object"||typeof r=="function")for(let s of a(r))!T.call(t,s)&&s!==e&&j(t,s,{get:()=>r[s],enumerable:!(o=v(r,s))||o.enumerable});return t};var m=(t,r,e)=>(e=t!=null?p(k(t)):{},f(r||!t||!t.__esModule?j(e,"default",{value:t,enumerable:!0}):e,t));var E=n(l=>{"use strict";var _=Symbol.for("react.transitional.element"),c=Symbol.for("react.fragment");function x(t,r,e){var o=null;if(e!==void 0&&(o=""+e),r.key!==void 0&&(o=""+r.key),"key"in r){e={};for(var s in r)s!=="key"&&(e[s]=r[s])}else e=r;return r=e.ref,{$$typeof:_,type:t,key:o,ref:r!==void 0?r:null,props:e}}l.Fragment=c;l.jsx=x;l.jsxs=x});var i=n((P,d)=>{"use strict";d.exports=E()});var u=m(i()),{Fragment:R,jsx:q,jsxs:C}=u,M=u.default??u;export{R as Fragment,M as default,q as jsx,C as jsxs};
/*! Bundled license information:

react/cjs/react-jsx-runtime.production.js:
  (**
   * @license React
   * react-jsx-runtime.production.js
   *
   * Copyright (c) Meta Platforms, Inc. and affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)
*/
//# sourceMappingURL=jsx-runtime.bundle.mjs.map