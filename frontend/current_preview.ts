type Render={revision:number;preview?:boolean};
export function currentPreview<T extends Render>(revision:number|undefined,dirty:boolean,exported:T|null|undefined,preview:T|null|undefined):T|null{
 if(dirty||revision===undefined)return null;
 return exported?.revision===revision?exported:preview?.revision===revision?preview:null;
}
