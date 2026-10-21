"use client";

import { Button } from "@/components/ui/button";
import { Checkbox, Select } from "@/components/ui/inputs";
import { DialogTrigger, Modal, Sheet, TriggerButton } from "@/components/ui/overlay";
import { Accordion, Tabs } from "@/components/ui/tabs";
import { showToast } from "@/components/ui/toast";

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
      <Button onClick={() => showToast("Search saved. We will email you new matches.", "success")} variant="secondary">
        Success toast
      </Button>
      <Button onClick={() => showToast("Your listing is now live.", "info")} variant="secondary">
        Info toast
      </Button>
      <Button onClick={() => showToast("We could not save your search.", "error")} variant="secondary">
        Error toast
      </Button>
      <Button
        onClick={() => {
          for (let i = 0; i < 10; i += 1) showToast("We could not save your search.", "error");
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
        { id: "overview", label: "Overview", content: <p>2019 Ford Fiesta 1.0 EcoBoost ST-Line, 42,150 miles.</p> },
        { id: "spec", label: "Specification", content: <p>Petrol, manual, 5 doors, 999 cc.</p> },
        { id: "history", label: "Vehicle history", content: <p>MOT valid until 14/03/2027.</p> },
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
        { id: "equipment", title: "Equipment", content: <p>Heated seats, rear camera, Apple CarPlay.</p> },
        { id: "running", title: "Running costs", content: <p>Road tax £190 a year. Likely ULEZ compliant.</p> },
        {
          id: "long",
          title: "A section title long enough to wrap onto two lines on a narrow phone screen",
          content: <p>Long titles wrap; the chevron stays at the end.</p>,
        },
      ]}
    />
  );
}
