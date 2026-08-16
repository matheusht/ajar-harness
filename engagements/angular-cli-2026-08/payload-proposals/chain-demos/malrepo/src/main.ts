import { bootstrapApplication } from '@angular/platform-browser';
import { Component } from '@angular/core';

@Component({ selector: 'app-root', template: '<h1>malrepo</h1>' })
export class App {}
bootstrapApplication(App).catch(() => {});
