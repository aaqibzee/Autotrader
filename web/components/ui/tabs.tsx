"use client";

import type { ReactNode } from "react";
import {
  Button as AriaButton,
  Disclosure,
  DisclosureGroup,
  DisclosurePanel,
  Heading,
  Tab,
  TabList,
  TabPanel,
  Tabs as AriaTabs,
} from "react-aria-components";
import { cx } from "./cx";

/**
 * Tabs and accordion (Feature 03 §2) on React Aria: arrow keys move between tabs,
 * `Home`/`End` jump, and each panel is labelled by its tab.
 */
export type TabItem = { id: string; label: ReactNode; content: ReactNode };

export function Tabs({
  label,
  items,
  defaultSelectedKey,
  className,
}: {
  /** Names the tab list for screen readers. */
  label: string;
  items: readonly TabItem[];
  defaultSelectedKey?: string;
  className?: string;
}) {
  return (
    <AriaTabs className={className} defaultSelectedKey={defaultSelectedKey}>
      <TabList
        aria-label={label}
        className="flex gap-1 overflow-x-auto border-b border-line"
      >
        {items.map((item) => (
          <Tab
            className={cx(
              "-mb-px inline-flex min-h-11 cursor-pointer items-center border-b-2 border-transparent px-4 text-sm font-semibold whitespace-nowrap text-ink-muted outline-none",
              "hover-state:text-ink data-selected:border-brand data-selected:text-ink",
              "data-focus-visible:outline-2 data-focus-visible:outline-offset-[-2px] data-focus-visible:outline-focus",
            )}
            id={item.id}
            key={item.id}
          >
            {item.label}
          </Tab>
        ))}
      </TabList>
      {items.map((item) => (
        <TabPanel
          className="py-4 outline-none data-focus-visible:outline-2 data-focus-visible:outline-focus"
          id={item.id}
          key={item.id}
        >
          {item.content}
        </TabPanel>
      ))}
    </AriaTabs>
  );
}

export type AccordionItem = {
  id: string;
  title: ReactNode;
  content: ReactNode;
};

/** Sections that expand in place, e.g. a listing's full spec (Feature 08). */
export function Accordion({
  items,
  allowsMultipleExpanded = true,
  defaultExpandedKeys,
  className,
}: {
  items: readonly AccordionItem[];
  allowsMultipleExpanded?: boolean;
  defaultExpandedKeys?: string[];
  className?: string;
}) {
  return (
    <DisclosureGroup
      allowsMultipleExpanded={allowsMultipleExpanded}
      className={cx(
        "divide-y divide-line rounded-lg border border-line bg-surface",
        className,
      )}
      defaultExpandedKeys={defaultExpandedKeys}
    >
      {items.map((item) => (
        <Disclosure className="group" id={item.id} key={item.id}>
          <Heading className="m-0">
            <AriaButton
              className="flex min-h-11 w-full items-center justify-between gap-4 px-4 text-left font-semibold text-ink outline-none hover-state:bg-sunken data-focus-visible:outline-2 data-focus-visible:outline-offset-[-2px] data-focus-visible:outline-focus"
              slot="trigger"
            >
              {item.title}
              <svg
                aria-hidden="true"
                className="size-4 shrink-0 transition-transform group-data-expanded:rotate-180 motion-reduce:transition-none"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </AriaButton>
          </Heading>
          <DisclosurePanel className="px-4 pb-4 text-ink-soft">
            {item.content}
          </DisclosurePanel>
        </Disclosure>
      ))}
    </DisclosureGroup>
  );
}
