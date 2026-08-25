"use client";

import { ArrowUp, CalendarSearch } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

type CalendarNavigatorProps = {
  availableDates: string[];
  displayedMonth: string;
  initialDate: string;
  today: string;
};

function nearestAvailableDate(target: string, availableDates: string[]) {
  if (!availableDates.length) return null;

  return availableDates.reduce((nearest, date) => {
    const nearestDistance = Math.abs(Date.parse(`${nearest}T00:00:00`) - Date.parse(`${target}T00:00:00`));
    const distance = Math.abs(Date.parse(`${date}T00:00:00`) - Date.parse(`${target}T00:00:00`));
    return distance < nearestDistance ? date : nearest;
  });
}

function scrollToDate(target: string, availableDates: string[], behavior: ScrollBehavior) {
  const date = nearestAvailableDate(target, availableDates);
  if (!date) return;

  document.getElementById(`date-${date}`)?.scrollIntoView({ behavior, block: "center" });
}

export function CalendarNavigator({ availableDates, displayedMonth, initialDate, today }: CalendarNavigatorProps) {
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    const target = initialDate || (displayedMonth === today.slice(0, 7) ? today : null);
    if (!target) return;

    setSelectedDate(target);
    const frame = window.requestAnimationFrame(() => scrollToDate(target, availableDates, "smooth"));
    return () => window.cancelAnimationFrame(frame);
  }, [availableDates, displayedMonth, initialDate, today]);

  useEffect(() => {
    const updateTopButton = () => setShowTop(window.scrollY > 500);
    updateTopButton();
    window.addEventListener("scroll", updateTopButton, { passive: true });
    return () => window.removeEventListener("scroll", updateTopButton);
  }, []);

  function jumpToDate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDate) return;

    const selectedMonth = selectedDate.slice(0, 7);
    if (selectedMonth !== displayedMonth) {
      window.location.assign(`/calendar?month=${selectedMonth}&date=${selectedDate}`);
      return;
    }

    window.history.replaceState(null, "", `/calendar?month=${displayedMonth}&date=${selectedDate}`);
    scrollToDate(selectedDate, availableDates, "smooth");
  }

  return (
    <>
      <form className="calendar-jump" onSubmit={jumpToDate}>
        <label htmlFor="calendar-jump-date">Go to date</label>
        <input
          id="calendar-jump-date"
          type="date"
          value={selectedDate}
          onChange={(event) => setSelectedDate(event.target.value)}
        />
        <button type="submit" aria-label="Go to selected date">
          <CalendarSearch aria-hidden="true" size={16} strokeWidth={1.7} />
          <span>Go</span>
        </button>
      </form>
      <button
        className={`calendar-to-top${showTop ? " is-visible" : ""}`}
        type="button"
        aria-label="Back to top"
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      >
        <ArrowUp aria-hidden="true" size={18} strokeWidth={1.7} />
      </button>
    </>
  );
}
