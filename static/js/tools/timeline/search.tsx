/**
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import axios from "axios";
import {} from "googlemaps";
import React, { Component, PureComponent } from "react";
import ReactDOM from "react-dom";

import { toTitleCase } from "../shared_util";

// Hardcoded results to respond to in the place autocomplete.
const HARDCODED_RESULTS = {
  africa: "africa",
  asia: "asia",
  earth: "Earth",
  europe: "europe",
  "north america": "northamerica",
  oceania: "oceania",
  "south america": "southamerica",
};

interface ChipPropType {
  placeName: string;
  placeId: string;
  removePlace: (place: string) => void;
}

class Chip extends PureComponent<ChipPropType, Record<string, unknown>> {
  constructor(props) {
    super(props);
    this.deleteChip = this.deleteChip.bind(this);
  }

  render() {
    return (
      <span className="mdl-chip mdl-chip--deletable">
        <span className="mdl-chip__text">{this.props.placeName}</span>
        <button className="mdl-chip__action" onClick={this.deleteChip}>
          <i className="material-icons">cancel</i>
        </button>
      </span>
    );
  }

  private deleteChip() {
    this.props.removePlace(this.props.placeId);
  }
}

interface SearchBarPropType {
  places: Record<string, string>;
  addPlace: (place: string) => void;
  removePlace: (place: string) => void;
  numPlacesLimit?: number; // Maximum number of places allowed
  countryRestrictions?: string[];
  customPlaceHolder?: string;
}

class SearchBar extends Component<SearchBarPropType> {
  inputElem: React.RefObject<HTMLInputElement>;
  ac: google.maps.places.Autocomplete;

  constructor(props: SearchBarPropType) {
    super(props);
    this.getPlaceAndRender = this.getPlaceAndRender.bind(this);
    this.inputElem = React.createRef();
    this.ac = null;
  }

  render(): JSX.Element {
    const placeIds = Object.keys(this.props.places);
    const hideInput = this.props.numPlacesLimit
      ? placeIds.length >= this.props.numPlacesLimit
      : false;
    return (
      <div id="location-field" className={hideInput ? "input-area-hidden" : ""}>
        <div id="search-icon"></div>
        <span id="prompt">Find : </span>
        <span id="place-list">
          {placeIds.map((placeId) => (
            <Chip
              placeId={placeId}
              placeName={
                this.props.places[placeId]
                  ? this.props.places[placeId]
                  : placeId
              }
              key={placeId}
              removePlace={this.props.removePlace}
            ></Chip>
          ))}
        </span>
        <input ref={this.inputElem} id="ac" type="text" />
        {!hideInput && <i className="material-icons search-icon">search</i>}
        <span id="place-name"></span>
      </div>
    );
  }

  componentDidMount(): void {
    // Create the autocomplete object, restricting the search predictions to
    // geographical location types.
    const options = {
      types: ["(regions)"],
      fields: ["place_id", "name", "types"],
    };
    if (this.props.countryRestrictions) {
      options["componentRestrictions"] = {
        country: this.props.countryRestrictions,
      };
    }
    if (google.maps) {
      this.ac = new google.maps.places.Autocomplete(
        this.inputElem.current,
        options
      );
      this.inputElem.current.addEventListener(
        "keyup",
        this.onAutocompleteKeyUp
      );
      this.ac.addListener("place_changed", this.getPlaceAndRender);
    }
    this.setPlaceholder();
  }

  componentDidUpdate(): void {
    this.setPlaceholder();
  }

  static getHardcodedResultDcid(inputVal: string): string {
    // Returns DCID of the hardcoded result, if there is a match. Undefined, if no match.
    return HARDCODED_RESULTS[inputVal.toLowerCase()];
  }

  private onAutocompleteKeyUp(e) {
    // Test for, and respond to, a few hardcoded results.
    const inputVal = (e.target as HTMLInputElement).value;
    const dcid = SearchBar.getHardcodedResultDcid(inputVal);
    if (dcid) {
      const containers = document.getElementsByClassName("pac-container");
      const displayResult = toTitleCase(inputVal);
      if (containers && containers.length) {
        const container = containers[0];
        // Keep this in sync with the Maps API results DOM.
        const result = (
          <div className="pac-item">
            <span className="pac-icon pac-icon-marker"></span>
            <span className="pac-item-query">
              <span className="pac-matched">{displayResult}</span>
            </span>
          </div>
        );
        container.prepend(ReactDOM.render(result, container));
      }
      // It's unreliable to listen to the ENTER event here. Handling of
      // these manually added results are done in getPlaceAndRender.
    }
  }

  private getPlaceAndRender() {
    // Get the place details from the autocomplete object.
    const place = this.ac.getPlace();
    if ("place_id" in place) {
      axios
        .get(`/api/place/placeid2dcid/${place.place_id}`)
        .then((resp) => {
          this.props.addPlace(resp.data);
        })
        .catch(() => {
          alert("Sorry, but we don't have any data about " + place.name);
        });
    }
    if ("name" in place) {
      // Handle hardcoded results.
      const inputVal = place["name"];
      const dcid = SearchBar.getHardcodedResultDcid(inputVal);
      if (dcid) {
        this.props.addPlace(dcid);
      }
    }
  }

  private setPlaceholder() {
    this.inputElem.current.value = "";
    const numPlaces = Object.keys(this.props.places).length;
    this.inputElem.current.disabled = false;
    if (numPlaces > 0) {
      if (
        this.props.numPlacesLimit !== undefined &&
        numPlaces >= this.props.numPlacesLimit
      ) {
        this.inputElem.current.placeholder = "";
        this.inputElem.current.disabled = true;
      } else {
        this.inputElem.current.placeholder = "Add another place";
      }
    } else {
      this.inputElem.current.placeholder = this.props.customPlaceHolder
        ? this.props.customPlaceHolder
        : "Enter a country, state, county, or city to get started";
    }
  }
}
export { SearchBar };
