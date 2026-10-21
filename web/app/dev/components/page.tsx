import { Button, IconButton } from "@/components/ui/button";
import {
  Badge,
  Card,
  ListingBadges,
  Skeleton,
  Tag,
} from "@/components/ui/display";
import {
  Checkbox,
  RadioGroup,
  Select,
  TextInput,
  Toggle,
} from "@/components/ui/inputs";
import { Breadcrumbs, Pagination } from "@/components/ui/navigation";
import {
  EmptyState,
  ErrorState,
  NotFound,
  PermissionDenied,
} from "@/components/ui/states";
import { PROBLEM_UI } from "@/lib/api/problem-ui";
import { galleryEnabled } from "@/lib/dev/gallery";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import {
  AccordionDemo,
  ComboboxDemos,
  OfflineDemos,
  OverlayDemos,
  ProblemDemos,
  RangeSliderDemos,
  TabsDemo,
  ToastDemos,
} from "./interactive-demos";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Component gallery",
  robots: { index: false },
};

/**
 * Every component in every state (Feature 03 §9): default, forced hover/focus, disabled,
 * loading, error, empty and long content. Only with `ENABLE_COMPONENT_GALLERY=1` (local,
 * CI e2e, staging; A3). Each section is anchored (`#buttons`, …) so screenshot tests can
 * capture one at a time (slice 3.14).
 */
export default function ComponentGalleryPage() {
  if (!galleryEnabled()) notFound();

  return (
    <main className="shell py-10">
      <h1 className="text-3xl font-semibold tracking-tight">
        Component gallery
      </h1>
      <p className="mt-2 text-ink-muted">
        Dev and staging only. Every state of every component.
      </p>
      <nav aria-label="Sections" className="mt-6 flex flex-wrap gap-2">
        {SECTIONS.map(([id, title]) => (
          // Inline text links: exempt from the 24px target minimum (SC 2.5.8 "inline").
          <a
            className="rounded-sm text-sm text-brand-strong underline"
            data-inline-link=""
            href={`#${id}`}
            key={id}
          >
            {title}
          </a>
        ))}
      </nav>

      <Section id="buttons" title="Buttons">
        {(["primary", "secondary", "ghost", "danger"] as const).map(
          (variant) => (
            <Row key={variant} label={variant}>
              <Button variant={variant}>Save search</Button>
              <Button data-force="hover" variant={variant}>
                Hover
              </Button>
              <Button data-force="focus" variant={variant}>
                Focus
              </Button>
              <Button disabled variant={variant}>
                Disabled
              </Button>
              <Button loading variant={variant}>
                Saving
              </Button>
            </Row>
          ),
        )}
        <Row label="sizes">
          <Button size="sm">Small (36px)</Button>
          <Button size="md">Medium (40px)</Button>
          <Button size="touch">Touch (44px)</Button>
        </Row>
        <Row label="long label">
          <Button className="max-w-64">
            Contact the dealer about this 2019 Ford Fiesta ST-Line
          </Button>
        </Row>
      </Section>

      <Section id="icon-buttons" title="Icon buttons">
        <Row label="states">
          <IconButton icon={<HeartIcon />} label="Save this car" />
          <IconButton
            data-force="hover"
            icon={<HeartIcon />}
            label="Save this car (hover)"
          />
          <IconButton
            data-force="focus"
            icon={<HeartIcon />}
            label="Save this car (focus)"
          />
          <IconButton
            disabled
            icon={<HeartIcon />}
            label="Save this car (disabled)"
          />
          <IconButton
            icon={<HeartIcon />}
            label="Save this car (small)"
            size="sm"
          />
          <IconButton
            icon={<FilterIcon />}
            label="Open filters"
            variant="secondary"
          />
        </Row>
      </Section>

      <Section id="text-inputs" title="Text inputs">
        <div className="grid gap-6 md:grid-cols-2">
          <TextInput
            id="gallery-postcode"
            label="Postcode"
            placeholder="e.g. SW1A 1AA"
          />
          <TextInput
            hint="We use it to show distances. We never share it."
            id="gallery-postcode-hint"
            label="Postcode"
          />
          <TextInput
            defaultValue="SW1A"
            error="Enter a full postcode, like SW1A 1AA."
            id="gallery-postcode-error"
            label="Postcode"
          />
          <TextInput data-force="focus" id="gallery-focus" label="Focused" />
          <TextInput
            defaultValue="Read only for now"
            disabled
            id="gallery-disabled"
            label="Disabled"
          />
          <TextInput
            defaultValue="A very long value that keeps going well past the width of the field on a phone"
            id="gallery-long"
            label="A label long enough to wrap onto a second line on a narrow phone screen"
          />
        </div>
      </Section>

      <Section id="selects" title="Selects">
        <div className="grid gap-6 md:grid-cols-2">
          <Select
            id="gallery-fuel"
            label="Fuel type"
            options={FUEL}
            placeholder="Any"
          />
          <Select
            defaultValue="diesel"
            id="gallery-fuel-set"
            label="Fuel type"
            options={FUEL}
          />
          <Select
            error="Choose a fuel type."
            id="gallery-fuel-error"
            label="Fuel type"
            options={FUEL}
            placeholder="Choose"
          />
          <Select
            disabled
            id="gallery-fuel-disabled"
            label="Fuel type (disabled)"
            options={FUEL}
          />
        </div>
      </Section>

      <Section id="choices" title="Checkbox, radio group, toggle">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <Checkbox id="gallery-ulez" label="Likely ULEZ compliant" />
            <Checkbox
              defaultChecked
              id="gallery-ulez-checked"
              label="Checked"
            />
            <Checkbox
              data-force="focus"
              id="gallery-ulez-focus"
              label="Focused"
            />
            <Checkbox disabled id="gallery-ulez-disabled" label="Disabled" />
            <Checkbox
              error="You must accept the terms to continue."
              id="gallery-terms"
              label="I accept the terms"
            />
          </div>
          <RadioGroup
            defaultValue="automatic"
            hint="Choose one."
            legend="Gearbox"
            name="gallery-gearbox"
            options={[
              { value: "manual", label: "Manual" },
              { value: "automatic", label: "Automatic" },
              { value: "other", label: "Other (unavailable)", disabled: true },
            ]}
          />
          <div>
            <Toggle id="gallery-alerts" label="Email me new matches" />
            <Toggle defaultChecked id="gallery-alerts-on" label="On" />
            <Toggle disabled id="gallery-alerts-disabled" label="Disabled" />
          </div>
        </div>
        <RadioGroup
          className="mt-6"
          error="Choose how we should contact you."
          legend="Contact preference (error)"
          name="gallery-contact"
          options={[
            { value: "email", label: "Email" },
            { value: "phone", label: "Phone" },
          ]}
        />
      </Section>

      <Section id="badges" title="Badges and tags">
        <Row label="tones">
          {(
            [
              "neutral",
              "brand",
              "success",
              "warning",
              "danger",
              "info",
              "inverse",
            ] as const
          ).map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </Row>
        <Row label="listing">
          <ListingBadges.Example />
          <ListingBadges.Reserved />
          <ListingBadges.Sold />
        </Row>
        <Row label="tags">
          <Tag>Automatic</Tag>
          <Tag>Petrol</Tag>
          <Tag>42,150 miles</Tag>
          <Tag>A tag with an unusually long piece of text in it</Tag>
        </Row>
      </Section>

      <Section id="cards" title="Card">
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-5">
            <h3 className="font-semibold">Card title</h3>
            <p className="mt-1 text-ink-muted">
              Cards hold related content. ListingCard (slice 3.12) builds on
              this.
            </p>
          </Card>
          <Card className="p-5">
            <h3 className="font-semibold">Empty card</h3>
          </Card>
        </div>
      </Section>

      <Section id="skeletons" title="Skeleton">
        <div
          aria-busy="true"
          aria-label="Loading example"
          className="grid max-w-md gap-3"
          role="status"
        >
          <Skeleton className="aspect-[4/3] w-full" />
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </Section>

      <Section id="pagination" title="Pagination">
        <Row label="first">
          <Pagination current={1} hrefFor={galleryPage} total={20} />
        </Row>
        <Row label="middle">
          <Pagination current={10} hrefFor={galleryPage} total={20} />
        </Row>
        <Row label="last">
          <Pagination current={20} hrefFor={galleryPage} total={20} />
        </Row>
        <Row label="few pages">
          <Pagination current={2} hrefFor={galleryPage} total={3} />
        </Row>
      </Section>

      <Section id="breadcrumbs" title="Breadcrumbs">
        <Breadcrumbs
          items={[
            { label: "Home", href: "/" },
            { label: "Used cars", href: "/search" },
            { label: "Ford", href: "/search?make=ford" },
            { label: "2019 Ford Fiesta 1.0 EcoBoost ST-Line 5dr" },
          ]}
        />
      </Section>

      <Section id="overlays" title="Modal and sheet">
        <OverlayDemos />
      </Section>

      <Section id="toasts" title="Toasts">
        <ToastDemos />
      </Section>

      <Section id="tabs" title="Tabs">
        <TabsDemo />
      </Section>

      <Section id="accordion" title="Accordion">
        <AccordionDemo />
      </Section>

      <Section id="combobox" title="Combobox">
        <ComboboxDemos />
      </Section>

      <Section id="range-slider" title="Range slider">
        <RangeSliderDemos />
      </Section>

      <Section id="states" title="Empty and error states">
        <div className="grid gap-6 lg:grid-cols-2">
          <EmptyState
            action={<Button variant="secondary">Clear filters</Button>}
            headingLevel={3}
            message="Try a wider radius, or remove a filter or two."
            title="No cars match your search"
          />
          <ErrorState
            headingLevel={3}
            requestId="req_server_rendered"
            ui={PROBLEM_UI.internal_error}
          />
          <PermissionDenied headingLevel={3} />
          <NotFound headingLevel={3} />
        </div>
        <h3 className="mt-8 text-lg font-semibold">
          From a thrown error (ProblemView)
        </h3>
        <div className="mt-4">
          <ProblemDemos />
        </div>
      </Section>

      <Section id="offline" title="Offline banner">
        <p className="mb-4 text-ink-soft">
          Shown at the top of every page. Go offline in the browser, or simulate
          a request that got no response while the browser still thinks it is
          online.
        </p>
        <OfflineDemos />
      </Section>
    </main>
  );
}

const SECTIONS = [
  ["buttons", "Buttons"],
  ["icon-buttons", "Icon buttons"],
  ["text-inputs", "Text inputs"],
  ["selects", "Selects"],
  ["choices", "Choices"],
  ["badges", "Badges"],
  ["cards", "Card"],
  ["skeletons", "Skeleton"],
  ["pagination", "Pagination"],
  ["breadcrumbs", "Breadcrumbs"],
  ["overlays", "Modal and sheet"],
  ["toasts", "Toasts"],
  ["tabs", "Tabs"],
  ["accordion", "Accordion"],
  ["combobox", "Combobox"],
  ["range-slider", "Range slider"],
  ["states", "States"],
  ["offline", "Offline banner"],
] as const;

const FUEL = [
  { value: "petrol", label: "Petrol" },
  { value: "diesel", label: "Diesel" },
  { value: "electric", label: "Electric" },
  { value: "hybrid", label: "Hybrid" },
];

const galleryPage = (page: number) => `/dev/components?page=${page}#pagination`;

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="mt-12 scroll-mt-6"
      id={id}
    >
      <h2
        className="border-b border-line pb-2 text-xl font-semibold"
        id={`${id}-title`}
      >
        {title}
      </h2>
      <div className="mt-4 grid gap-4">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[8rem_1fr] sm:items-center">
      <span className="font-mono text-xs text-ink-muted uppercase">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

function HeartIcon() {
  return (
    <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z" />
    </svg>
  );
}

function FilterIcon() {
  return (
    <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path d="M4 6h16M7 12h10M10 18h4" />
    </svg>
  );
}
