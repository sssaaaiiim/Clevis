import React from "react";

export default function ConstellationLogo({ size = 32, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={className} fill="none">
      <path d="M7 8.5 16 5l9 5.5-2 12-10 4L6 19l1-10.5Z" stroke="#8FB9EB" strokeWidth="1.15" strokeLinejoin="round" />
      <path d="m7 8.5 9 6 9-4M16 14.5l-3 12M16 14.5l7 8" stroke="#C6DDF7" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="7" cy="8.5" r="2" fill="#F4F8FE" />
      <circle cx="16" cy="5" r="2" fill="#81B7F0" />
      <circle cx="25" cy="10.5" r="2" fill="#F4F8FE" />
      <circle cx="16" cy="14.5" r="2.5" fill="#5B9BE6" stroke="#F4F8FE" strokeWidth="1" />
      <circle cx="6" cy="19" r="2" fill="#81B7F0" />
      <circle cx="13" cy="26.5" r="2" fill="#F4F8FE" />
      <circle cx="23" cy="22.5" r="2" fill="#81B7F0" />
    </svg>
  );
}
