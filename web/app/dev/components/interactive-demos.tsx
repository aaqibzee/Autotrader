"use client";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { RangeSlider } from "@/components/ui/range-slider";
import { formatMileage, formatPrice } from "@/lib/format";
import { Checkbox, Select } from "@/components/ui/inputs";
import {
  DialogTrigger,
  Modal,
  Sheet,
  TriggerButton,
} from "@/components/ui/overlay";
import { Accordion, Tabs } from "@/components/ui/tabs";
import { showToast } from "@/components/ui/toast";
import { GALLERY_MAKES } from "./fixtures";

/** Gallery demos for the React Aria components (slice 3.7). Client-only by nature. */
export function OverlayDemos() {
  return (
    <div className="flex flex-wrap gap-3">
      <DialogTrigger>
        <TriggerButton>Open modal</TriggerButton>
        <Modal
          footer={(close) => (
            <div className="flex justify-end gap-2">
              <Button onClick={close} variant="secondary">
                Cancel
              </Button>
              <Button onClick={close} variant="danger">
                Delete
              </Button>
            </div>
          )}
          title="Delete this saved search?"
        >
          <p>You will stop getting emails for it. This cannot be undone.</p>
        </Modal>
      </DialogTrigger>

      <DialogTrigger>
        <TriggerButton size="touch" variant="primary">
          Filters
        </TriggerButton>
        <Sheet
          footer={(close) => (
            <Button className="w-full" onClick={close} size="touch">
              Show 1,204 cars
            </Button>
          )}
          title="Filters"
        >
          <div className="grid gap-4">
            <Combobox
              id="sheet-make"
              items={GALLERY_MAKES}
              label="Make"
              placeholder="Any make"
            />
            <PriceRange />
            <Select
              id="sheet-fuel"
              label="Fuel type"
              options={[
                { value: "petrol", label: "Petrol" },
                { value: "diesel", label: "Diesel" },
              ]}
              placeholder="Any"
            />
            <Checkbox id="sheet-ulez" label="Likely ULEZ compliant" />
          </div>
        </Sheet>
      </DialogTrigger>
    </div>
  );
}

export function ToastDemos() {
  return (
    <div className="flex flex-wrap gap-3">
      <Button
        onClick={() =>
          showToast("Search saved. We will email you new matches.", "success")
        }
        variant="secondary"
      >
        Success toast
      </Button>
      <Button
        onClick={() => showToast("Your listing is now live.", "info")}
        variant="secondary"
      >
        Info toast
      </Button>
      <Button
        onClick={() => showToast("We could not save your search.", "error")}
        variant="secondary"
      >
        Error toast
      </Button>
      <Button
        onClick={() => {
          for (let i = 0; i < 10; i += 1)
            showToast("We could not save your search.", "error");
        }}
        variant="secondary"
      >
        Ten identical errors (shows one)
      </Button>
    </div>
  );
}

export function TabsDemo() {
  return (
    <Tabs
      items={[
        {
          id: "overview",
          label: "Overview",
          content: <p>2019 Ford Fiesta 1.0 EcoBoost ST-Line, 42,150 miles.</p>,
        },
        {
          id: "spec",
          label: "Specification",
          content: <p>Petrol, manual, 5 doors, 999 cc.</p>,
        },
        {
          id: "history",
          label: "Vehicle history",
          content: <p>MOT valid until 14/03/2027.</p>,
        },
      ]}
      label="Listing details"
    />
  );
}

export function AccordionDemo() {
  return (
    <Accordion
      defaultExpandedKeys={["equipment"]}
      items={[
        {
          id: "equipment",
          title: "Equipment",
          content: <p>Heated seats, rear camera, Apple CarPlay.</p>,
        },
        {
          id: "running",
          title: "Running costs",
          content: <p>Road tax £190 a year. Likely ULEZ compliant.</p>,
        },
        {
          id: "long",
          title:
            "A section title long enough to wrap onto two lines on a narrow phone screen",
          content: <p>Long titles wrap; the chevron stays at the end.</p>,
        },
      ]}
    />
  );
}

export function ComboboxDemos() {
  return (
    <div className="grid max-w-md gap-6">
      <Combobox
        hint="Try “citroen” or “mercedes benz”."
        id="demo-make"
        items={GALLERY_MAKES}
        label="Make"
        placeholder="Any make"
      />
      <Combobox
        id="demo-make-selected"
        defaultSelectedKey="skoda"
        items={GALLERY_MAKES}
        label="Make (selected)"
      />
      <Combobox
        id="demo-model-loading"
        isLoading
        items={[]}
        label="Model (loading)"
        placeholder="Loading models…"
      />
      <Combobox
        error="Choose a make."
        id="demo-make-error"
        items={GALLERY_MAKES}
        label="Make (error)"
      />
      <Combobox
        id="demo-make-disabled"
        isDisabled
        items={GALLERY_MAKES}
        label="Make (disabled)"
        placeholder="Choose a make first"
      />
    </div>
  );
}

/** Price in pence, £500 steps up to £100,000. */
function PriceRange() {
  return (
    <RangeSlider
      defaultValue={[500_000, 2_000_000]}
      formatValue={formatPrice}
      label="Price"
      maxValue={10_000_000}
      minValue={0}
      names={["price_min", "price_max"]}
      step={50_000}
      thumbLabels={["Minimum", "Maximum"]}
    />
  );
}

export function RangeSliderDemos() {
  return (
    <div className="grid max-w-md gap-8">
      <PriceRange />
      <RangeSlider
        defaultValue={[10_000, 60_000]}
        formatValue={formatMileage}
        label="Mileage"
        maxValue={200_000}
        minValue={0}
        step={1_000}
        thumbLabels={["Minimum", "Maximum"]}
      />
      <RangeSlider
        defaultValue={[2_000_000, 2_000_000]}
        formatValue={formatPrice}
        label="Price (thumbs together)"
        maxValue={10_000_000}
        minValue={0}
        step={50_000}
        thumbLabels={["Minimum", "Maximum"]}
      />
      <RangeSlider
        formatValue={formatMileage}
        isDisabled
        label="Mileage (disabled)"
        maxValue={200_000}
        minValue={0}
        step={1_000}
        thumbLabels={["Minimum", "Maximum"]}
      />
    </div>
  );
}
