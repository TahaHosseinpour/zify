"use client";
import React from "react";

interface StarBorderProps {
  as?: React.ElementType;
  className?: string;
  innerClassName?: string;
  children?: React.ReactNode;
  color?: string;
  speed?: string;
  thickness?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export default function StarBorder({
  as: Tag = "button",
  className = "",
  innerClassName = "",
  color = "white",
  speed = "6s",
  thickness = 1,
  children,
  style,
  ...rest
}: StarBorderProps) {
  return (
    <Tag
      className={`relative inline-flex overflow-hidden ${className}`}
      style={{ padding: `${thickness}px 0`, ...style }}
      {...rest}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute w-[300%] h-[50%] opacity-70 bottom-[-11px] right-[-250%] rounded-full"
        style={{
          background: `radial-gradient(circle, ${color}, transparent 10%)`,
          animation: `star-movement-bottom ${speed} linear infinite alternate`,
          zIndex: 0,
        }}
      />
      <span
        aria-hidden
        className="pointer-events-none absolute w-[300%] h-[50%] opacity-70 top-[-10px] left-[-250%] rounded-full"
        style={{
          background: `radial-gradient(circle, ${color}, transparent 10%)`,
          animation: `star-movement-top ${speed} linear infinite alternate`,
          zIndex: 0,
        }}
      />
      <span
        className={`relative flex items-center gap-2 ${innerClassName}`}
        style={{ zIndex: 1 }}
      >
        {children}
      </span>
    </Tag>
  );
}
