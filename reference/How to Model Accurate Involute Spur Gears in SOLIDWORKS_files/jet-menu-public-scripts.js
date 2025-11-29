( function( $ ) {
	'use strict';

	/**
	 * JetMegaMenuClass
	 */
	class JetMegaMenuClass {

		/**
		 * [constructor description]
		 * @return {[type]} [description]
		 */
		constructor( instance, options ) {
			this.defaultSettings = {
				menuId: '0',
				menuUniqId: window.jetMenu.getUniqId(),
				layout: 'horizontal',
				subTrigger: 'item', // item, submarker
				subEvent: 'click', // hover, click
				subCloseBehavior: 'mouseleave', // mouseleave, outside
				rollUp: true,
				breakpoint: 768, // Minimal menu width, when this plugin activates
				mouseLeaveDelay: 500,
				megaWidthType: 'container',
				megaWidthSelector: '',
				megaAjaxLoad: false,
				classes: {
					instance: 'menu',
					menuContainer: 'menu-container',
					menuList: 'menu-list',
					menuItem: 'menu-item',
					menuItemLink: 'menu-item__link',
					subMenuContainer: 'sub-menu',
					subMenuList: 'sub-menu__list',
					megaContainer: 'mega-container',
				}
			}

			this.$instance = $( instance );
			this.settings = $.extend( this.defaultSettings, options );
			this.$window = $( window );
			this.$document = $( document );
			this.$body = $( 'body' );
			this.isRTL = this.$body.hasClass( 'rtl' );
			this.isDropdownState = false;

			this._prevViewportWidth = window.innerWidth || document.documentElement.clientWidth;

			this.createInstance();
		}

		createInstance() {
			this.$menuList = $( `.${ this.settings.classes.menuList }`, this.$instance );
			this.$menuItems = $( `>.${ this.settings.classes.menuItem }:not(.${ this.settings.classes.menuItem }--roll-up)`, this.$menuList );
			this.$rollUpItem = $( `>.${ this.settings.classes.menuItem }--roll-up`, this.$menuList );

			this.menuItemsData = this.$menuItems.toArray().map( function( item ) {
				return {
					element: item,
					outerWidth: $( item ).outerWidth( true ),
					offsetLeft: $( item )[0].offsetLeft,
				}
			} );

			this.initWatcher( 50 );
			this.initEvents();
			this.maybeRollUpItems();
			this.rebuildSubContainers();

			document.addEventListener( 'DOMContentLoaded', ( event ) => {
				setTimeout( () => {
					this.watchTick();
				}, 250 );
			} );

			this.$instance.addClass( `${ this.settings.classes.instance }--inited` );
			this.$document.trigger( 'JetMegaMenuInited' );
		}

		initEvents() {
			let debounceTimer,
				eventHandler = 'JetMegaMenu',
				$itemTargetSelector = 'item' === this.settings.subTrigger ? `.${ this.settings.classes.menuItem } > .${ this.settings.classes.menuItem }__inner` : `.${ this.settings.classes.menuItem } > .${ this.settings.classes.menuItem }__inner .${ this.settings.classes.menuItem }__dropdown`;

			const subCloseBehavior   = this.settings.subCloseBehavior || 'mouseleave';
			const isHoverMode        = this.settings.subEvent === 'hover';
			const isClickMode        = this.settings.subEvent === 'click';
			const shouldCloseOnLeave = isHoverMode || ( isClickMode && subCloseBehavior === 'mouseleave' );
			const shouldCloseOnOutside = isClickMode && subCloseBehavior === 'outside';

			switch ( this.settings.subEvent ) {
				case 'hover':
					this.$instance.on( `mouseenter.${ eventHandler }`, `.${ this.settings.classes.menuItem } > .${ this.settings.classes.menuItem }__inner`, { instance: this }, ( event ) => {
						let $target       = $( event.target ),
							$menuItem     = $target.parents( `.${ this.settings.classes.menuItem }` ),
							$subContainer = $( `.${ this.settings.classes.subMenuContainer }:first, .${ this.settings.classes.megaContainer }:first`, $menuItem ),
							templateContent = $subContainer.data( 'template-content' ) || false,
							templateId    = $subContainer.data( 'template-id' ) || false;

						$( `.${ this.settings.classes.menuItem }--hover`, this.$instance ).removeClass( `${ this.settings.classes.menuItem }--hover` );

						if ( $menuItem.hasClass( `${ this.settings.classes.menuItem }-has-children` ) ) {
							$menuItem.addClass( `${ this.settings.classes.menuItem }--hover` );

							$menuItem
								.find( '[role="button"][aria-haspopup="true"]' )
								.attr( 'aria-expanded', 'true' );

							if ( templateId ) {
								this.maybeTemplateLoad( templateId, templateContent, $subContainer );
							}
						}
					} );

					this.$instance.on( `mouseleave.${ eventHandler }`, `.${ this.settings.classes.menuItem } > .${ this.settings.classes.menuItem }__inner`, ( event ) => { /* Item Mouse Leave Event */ } );
					break;

				case 'click':

					this.$instance.on( `click.${ eventHandler }`, $itemTargetSelector, ( event ) => {
						event.preventDefault();
						event.stopPropagation();

						let $currentTarget  = $( event.currentTarget ),
						    $menuItem       = $currentTarget.closest( `.${this.settings.classes.menuItem}` ),
						    $menuItemLink   = $( '.jet-mega-menu-item__link', $menuItem ).first(),
						    $siblingsItems  = $menuItem.siblings( `.${this.settings.classes.menuItem}-has-children` ),
						    $subContainer   = $( `.${this.settings.classes.subMenuContainer}:first, .${this.settings.classes.megaContainer}`, $menuItem ),
						    templateContent = $subContainer.data( 'template-content' ) || false,
						    templateId      = $subContainer.data( 'template-id' ) || false;

						if ( $siblingsItems.length ) {
							$siblingsItems.removeClass( `${ this.settings.classes.menuItem }--hover` );
							$( `.${ this.settings.classes.menuItem }-has-children`, $siblingsItems ).removeClass( `${ this.settings.classes.menuItem }--hover` );
						}

						if ( $menuItem.hasClass( `${ this.settings.classes.menuItem }-has-children` ) ) {
							if ( ! $menuItem.hasClass( `${ this.settings.classes.menuItem }--hover` ) ) {
								$menuItem.addClass( `${ this.settings.classes.menuItem }--hover` );

								$menuItem
									.find( '[role="button"][aria-haspopup="true"]' )
									.attr( 'aria-expanded', 'true' );

							} else {
								$menuItem.removeClass( `${ this.settings.classes.menuItem }--hover` );

								$menuItem
									.find( '[role="button"][aria-haspopup="true"]' )
									.attr( 'aria-expanded', 'false' );
							}

							if ( templateId ) {
								this.maybeTemplateLoad( templateId, templateContent, $subContainer );
							}
						} else {
							let itemLink = $menuItemLink.attr( 'href' ) || '#',
							    target   = $menuItemLink.attr( 'target' ) || '_self';

							window.open( itemLink, target );

							return false;
						}
					} );
					break;
			}

			this.$instance.on( `mouseenter.${ eventHandler }`, `.${ this.settings.classes.subMenuContainer }, .${ this.settings.classes.megaContainer }`, ( event ) => {
				clearTimeout( debounceTimer );
			} );

			this.$instance.on( `mouseenter.${ eventHandler }`, ( event ) => {
				clearTimeout( debounceTimer );
			} );

			this.$instance.on( `mouseleave.${ eventHandler }`, ( event ) => {

				if ( ! shouldCloseOnLeave ) {
					return;
				}

				debounceTimer = setTimeout( () => {
					$( `.${ this.settings.classes.menuItem }--hover`, this.$instance ).removeClass( `${ this.settings.classes.menuItem }--hover` );

					this.$instance
						.find( '[role="button"][aria-haspopup="true"]' )
						.attr( 'aria-expanded', 'false' );

				}, this.settings.mouseLeaveDelay );
			} );

			this.$document.on( `click.${ eventHandler }`, ( event ) => {

				if ( ! shouldCloseOnOutside ) {
					return;
				}

				this.closeOnOutside( event );
			} );

			this.$window.on( `orientationchange.${ eventHandler } resize.${ eventHandler }`, ( event ) => {
				const viewportWidth = window.innerWidth || document.documentElement.clientWidth;

				if ( viewportWidth === this._prevViewportWidth ) {
					return;
				}

				this._prevViewportWidth = viewportWidth;

				$( `.${ this.settings.classes.menuItem }`, this.$instance ).removeClass( `${ this.settings.classes.menuItem }--hover` );
				this.$instance.removeClass( `${ this.settings.classes.instance }--dropdown-open` );
			} );

			this.$document.on( `touchend.${ eventHandler }`, ( event ) => {
				this.closeOnOutside( event );
			} );

			this.$instance.on( 'watchTickEventResetRegularState', ( event ) => {
				this.resetRegularState();

				if ( this.$rollUpItem[0] ) {
					$( `.${ this.settings.classes.subMenuList }:first`, this.$rollUpItem ).empty();
					this.$rollUpItem[0].hidden = true;
				}

				for ( let index = 0; index < this.menuItemsData.length; index++ ) {
					this.menuItemsData[ index ].element.hidden = false;
				}
			} );

			this.$instance.on( 'watchTickEventResetDropdownState', ( event ) => {
				this.resetDropdownState();
				this.$instance.removeClass( `${ this.settings.classes.instance }--dropdown-open` );
			} );

			this.$instance.on( `click.${ eventHandler }`, `.${ this.settings.classes.instance }-toggle`,   ( event ) => {

				if ( ! this.$instance.hasClass( `${ this.settings.classes.instance }--dropdown-open` ) ) {
					this.$instance.addClass( `${ this.settings.classes.instance }--dropdown-open` );
				} else {
					this.$instance.removeClass( `${ this.settings.classes.instance }--dropdown-open` );
				}
			} );

			this.$instance.on( `keydown.${ eventHandler }`, `.${ this.settings.classes.menuItem }__inner[role="button"], .${ this.settings.classes.menuItem }__dropdown[role="button"]`, ( event ) => {

				if ( event.key === 'Enter' || event.key === ' ' ) {
					event.preventDefault();

					if ( this.settings.subEvent === 'click' ) {
						$( event.currentTarget ).trigger( 'click' );
					}

					if ( this.settings.subEvent === 'hover' ) {
						$( event.currentTarget ).trigger( 'mouseenter' );
					}
				}

			});

		}

		/**
		 * Init watcher function.
		 *
		 * @param  {number} Watcher debounce delay.
		 * @return {void}
		 */
		initWatcher( delay = 10 ) {
			$( window ).off( `resize.JetMegaMenu${ this.settings['menuUniqId'] }` ).on( `resize.JetMegaMenu${ this.settings['menuUniqId'] } orientationchange.JetMegaMenu${ this.settings['menuUniqId'] }`, this.debounce( delay, this.watchTick.bind( this ) ) );
			this.$instance.trigger( 'containerResize' );
		}

		/**
		 * Close submenu when a pointer event happens outside of the menu.
		 *
		 * @param  {Event} event ( click/touchend )
		 * @return {void}
		 */
		closeOnOutside( event ) {

			if ( $( event.target ).closest( `.${ this.settings.classes.menuItem }, .${ this.settings.classes.subMenuContainer }, .${ this.settings.classes.megaContainer }` ).length ) {
				return;
			}

			$( `.${ this.settings.classes.menuItem }`, this.$instance ).removeClass( `${ this.settings.classes.menuItem }--hover` );
			this.$instance.find( '[role="button"][aria-haspopup="true"]' ).attr( 'aria-expanded', 'false' );
		}

		/**
		 * Responsive menu watcher callback.
		 *
		 * @param  {Object} Resize or Orientationchange event.
		 * @return {void}
		 */
		watchTick( event ) {

			if ( this.isDropdown() ) {

				if ( ! this.isDropdownState ) {
					this.$instance.trigger( 'watchTickEventResetRegularState' );
				}

				this.isDropdownState = true;
				this.$instance.removeClass( `${ this.settings.classes.instance }--layout-horizontal ${ this.settings.classes.instance }--layout-vertical` );
				this.$instance.addClass( `${ this.settings.classes.instance }--layout-dropdown` );
				this.$instance.trigger( 'watchTickEventDropdown' );
			} else {

				if ( this.isDropdownState ) {
					this.$instance.trigger( 'watchTickEventResetDropdownState' );
				}

				this.isDropdownState = false;
				this.$instance.removeClass( `${ this.settings.classes.instance }--layout-dropdown` );
				this.$instance.addClass( `${ this.settings.classes.instance }--layout-${ this.settings.layout }` );
				this.$instance.trigger( `watchTickEventRegular` );
				this.$instance.trigger( `watchTickEventRegular--${ this.settings.layout }` );
			}

			this.$instance.trigger( 'watchTickEvent' );
		}

		/**
		 * Rollup rebuilding function.
		 *
		 * @return {void}
		 */
		maybeRollUpItems() {
			this.$instance.on( 'watchTickEventRegular--horizontal', ( event ) => {

				if ( ! this.settings.rollUp ) {
					return false;
				}

				let mainMenuWidth     = this.$instance.width(),
					rollUpWidth = this.$rollUpItem.outerWidth( true ),
				    visibleItemsArray = [],
				    hiddenItemsArray  = [];

				const minOffset = Math.min(...this.menuItemsData.map( d => d.offsetLeft ) );

				for ( let index = 0; index < this.menuItemsData.length; index++ ) {
					let itemData     = this.menuItemsData[ index ],
					    nextItemData = this.menuItemsData[ index + 1 ] || false,
						rightEdge    = ( nextItemData ? nextItemData.offsetLeft : itemData.offsetLeft + itemData.outerWidth ) - minOffset,
					    item         = itemData.element;

					if ( rightEdge + rollUpWidth > mainMenuWidth ) {
						item.hidden = true;
						hiddenItemsArray.push( item );
					} else {
						item.hidden = false;
						visibleItemsArray.push( item );
					}
				}

				$( `.${ this.settings.classes.subMenuList }:first`, this.$rollUpItem ).empty();

				for ( let hiddenMenuItem of hiddenItemsArray ) {
					let $hiddenClone = $( hiddenMenuItem ).clone();

					$hiddenClone[0].hidden = false;

					$( `>.${ this.settings.classes.menuItem }__inner >.${ this.settings.classes.menuItemLink }`, $hiddenClone ).toggleClass( `${ this.settings.classes.menuItemLink }--top-level ${ this.settings.classes.menuItemLink }--sub-level` );
					$( `.${ this.settings.classes.subMenuList }:first`, this.$rollUpItem ).append( $hiddenClone );
				}

				if ( this.$rollUpItem[0] ) {
					this.$rollUpItem[0].hidden = hiddenItemsArray.length ? false : true;
				}

				this.$instance.trigger( 'rollUpItemsEvent' );
			} )
		}

		/**
		 * Rebuild SubContainers function.
		 *
		 * @return {void}
		 */
		rebuildSubContainers() {
			this.$instance.on( 'watchTickEventRegular--horizontal', ( event ) => {
				let $megaMenuList   = $( `.${ this.settings.classes.megaContainer }`, this.$instance ),
				    $subMenuList    = $( `.${ this.settings.classes.subMenuContainer }`, this.$instance ),
				    subInverseClass = `${ this.settings.classes.subMenuContainer }--inverse`,
				    instanceWidth   = this.$instance.width(),
				    instanceOffset  = this.$instance.offset();

				$subMenuList.each( ( index, element ) => {
					let $element = $( element );

					if ( this.isOffscreenX( element ) ) {
						$element.addClass( subInverseClass );
					} else {
						$element.removeClass( subInverseClass );
					}
				} );

				switch( this.settings.megaWidthType ) {
					case 'container':
						$megaMenuList.each( ( index, element ) => {
							let $element           = $( element ),
							    $elementPosition = $element.data( 'position' ),
							    elementOffset      = $element.offset(),
							    elementDeltaOffset = 'default' === $elementPosition ? Math.ceil( instanceOffset.left - elementOffset.left ) : 0;

							$element.css( {
								'--jmm-submenu-width': `${ instanceWidth }px`,
								'--jmm-submenu-delta-x-offset': `${ elementDeltaOffset }px`
							} );
						} );

						break;
					case 'selector':
						let $customSelector = $( this.settings.megaWidthSelector );

						if ( $customSelector[0] ) {
							let selectorWidth = $customSelector.width(),
							    selectorOffset = Math.round( $customSelector.offset().left );

							document.fonts.ready.then( () => {
								$megaMenuList.each( ( index, element ) => {
									let $element           = $( element ),
										$elementPosition   = $element.data( 'position' ),
										elementOffset      = Math.round( $element.offset().left ),
										elementDeltaOffset = 'default' === $elementPosition ? Math.round( selectorOffset - elementOffset ) : 0;

									$element.css( {
										'--jmm-submenu-width': `${ selectorWidth }px`,
										'--jmm-submenu-delta-x-offset': `${ elementDeltaOffset }px`
									} );
								} );
							} );

						}

						break;
					case 'items':
						let $lastItem        = $( `.${ this.settings.classes.menuItem }--top-level:not([hidden]):last`, this.$instance ),
						    $firstItem        = $( `.${ this.settings.classes.menuItem }--top-level:not([hidden]):first`, this.$instance ),
						    lastItemBounding = $lastItem[0].getBoundingClientRect(),
						    firstItemBounding = $firstItem[0].getBoundingClientRect(),
						    itemsWidth       = lastItemBounding.x + lastItemBounding.width  - firstItemBounding.x;

						$megaMenuList.each( ( index, element ) => {
							let $element           = $( element ),
							    $elementPosition   = $element.data( 'position' ),
							    elementOffset      = $element.offset(),
							    elementDeltaOffset = 'default' === $elementPosition ? Math.ceil( instanceOffset.left - elementOffset.left ) : 0;

							$element.css( {
								'--jmm-submenu-width': `${ itemsWidth }px`,
								'--jmm-submenu-delta-x-offset': `${ elementDeltaOffset }px`
							} );
						} );
						break;
				}
			} );

			this.$instance.on( 'watchTickEventRegular--vertical', ( event ) => {
				let $megaMenuList    = $( `.${ this.settings.classes.megaContainer }`, this.$instance ),
				    $subMenuList     = $( `.${ this.settings.classes.subMenuContainer }`, this.$instance ),
				    instanceWidth    = this.$instance.width(),
				    instanceHeight   = this.$instance.height(),
				    instanceOffset   = this.$instance.offset(),
					windowWidth      = this.$window.outerWidth( true ),
					subInverseClass  = `${ this.settings.classes.subMenuContainer }--inverse`,
					megaInverseClass = `${ this.settings.classes.megaContainer }--inverse`;

				$subMenuList.each( ( index, element ) => {
					let $element = $( element );

					if ( this.isOffscreenX( element ) ) {
						$element.addClass( subInverseClass );
					} else {
						$element.removeClass( subInverseClass );
					}
				} );

				$megaMenuList.each( ( index, element ) => {
					let $element            = $( element ),
					    $elementPosition    = $element.data( 'position' ),
					    $parentElement      = $element.parent(),
					    elementOffset       = $element.offset(),
					    elementDeltaOffsetX = ( instanceOffset.left - elementOffset.left ) + instanceWidth,
					    elementDeltaOffsetY = 'default' === $elementPosition ? ( instanceOffset.top - elementOffset.top ) : 0,
					    elementDeltaWidth   = ( elementDeltaOffsetX + $element.width() );

					if ( $parentElement.hasClass(`${ this.settings.classes.menuItem }--top-level` ) ) {
						$element.css( {
							//'--jmm-submenu-width': `${ instanceWidth }px`,
							'--jmm-submenu-min-height': `${ instanceHeight }px`,
							//'--jmm-submenu-delta-x-offset': `${ elementDeltaOffsetX }px`,
							'--jmm-submenu-delta-y-offset': `${ elementDeltaOffsetY }px`
						} );
					}

					if ( this.isOffscreenX( element ) ) {
						$element.addClass( megaInverseClass );
					} else {
						$element.removeClass( megaInverseClass );
					}
				} );
			} );
		}

		/**
		 * Reset Regular State
		 *
		 * @return {void}
		 */
		resetRegularState() {}

		/**
		 * Reset Dropdown State
		 *
		 * @return {void}
		 */
		resetDropdownState() {}

		/**
		 * Get mobile status.
		 *
		 * @return {boolean} Mobile Status
		 */
		isDropdown() {
			return ( this.$window.width() < this.settings.breakpoint || 'dropdown' === this.settings.layout ) ? true : false;
		}

		/**
		 *
		 * @param element
		 * @returns {boolean}
		 */
		isOffscreenX( element ) {
			let rect = element.getBoundingClientRect();

			return (
				rect.x < 0 || ( rect.x + rect.width ) > window.innerWidth
			);
		}

		/**
		 * Mobile and tablet check funcion.
		 *
		 * @return {boolean} Mobile Status
		 */
		mobileAndTabletcheck() {
			let check = false;

			(function(a){if(/(android|bb\d+|meego).+mobile|avantgo|bada\/|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od)|iris|kindle|lge |maemo|midp|mmp|mobile.+firefox|netfront|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\/|plucker|pocket|psp|series(4|6)0|symbian|treo|up\.(browser|link)|vodafone|wap|windows ce|xda|xiino|android|ipad|playbook|silk/i.test(a)||/1207|6310|6590|3gso|4thp|50[1-6]i|770s|802s|a wa|abac|ac(er|oo|s\-)|ai(ko|rn)|al(av|ca|co)|amoi|an(ex|ny|yw)|aptu|ar(ch|go)|as(te|us)|attw|au(di|\-m|r |s )|avan|be(ck|ll|nq)|bi(lb|rd)|bl(ac|az)|br(e|v)w|bumb|bw\-(n|u)|c55\/|capi|ccwa|cdm\-|cell|chtm|cldc|cmd\-|co(mp|nd)|craw|da(it|ll|ng)|dbte|dc\-s|devi|dica|dmob|do(c|p)o|ds(12|\-d)|el(49|ai)|em(l2|ul)|er(ic|k0)|esl8|ez([4-7]0|os|wa|ze)|fetc|fly(\-|_)|g1 u|g560|gene|gf\-5|g\-mo|go(\.w|od)|gr(ad|un)|haie|hcit|hd\-(m|p|t)|hei\-|hi(pt|ta)|hp( i|ip)|hs\-c|ht(c(\-| |_|a|g|p|s|t)|tp)|hu(aw|tc)|i\-(20|go|ma)|i230|iac( |\-|\/)|ibro|idea|ig01|ikom|im1k|inno|ipaq|iris|ja(t|v)a|jbro|jemu|jigs|kddi|keji|kgt( |\/)|klon|kpt |kwc\-|kyo(c|k)|le(no|xi)|lg( g|\/(k|l|u)|50|54|\-[a-w])|libw|lynx|m1\-w|m3ga|m50\/|ma(te|ui|xo)|mc(01|21|ca)|m\-cr|me(rc|ri)|mi(o8|oa|ts)|mmef|mo(01|02|bi|de|do|t(\-| |o|v)|zz)|mt(50|p1|v )|mwbp|mywa|n10[0-2]|n20[2-3]|n30(0|2)|n50(0|2|5)|n7(0(0|1)|10)|ne((c|m)\-|on|tf|wf|wg|wt)|nok(6|i)|nzph|o2im|op(ti|wv)|oran|owg1|p800|pan(a|d|t)|pdxg|pg(13|\-([1-8]|c))|phil|pire|pl(ay|uc)|pn\-2|po(ck|rt|se)|prox|psio|pt\-g|qa\-a|qc(07|12|21|32|60|\-[2-7]|i\-)|qtek|r380|r600|raks|rim9|ro(ve|zo)|s55\/|sa(ge|ma|mm|ms|ny|va)|sc(01|h\-|oo|p\-)|sdk\/|se(c(\-|0|1)|47|mc|nd|ri)|sgh\-|shar|sie(\-|m)|sk\-0|sl(45|id)|sm(al|ar|b3|it|t5)|so(ft|ny)|sp(01|h\-|v\-|v )|sy(01|mb)|t2(18|50)|t6(00|10|18)|ta(gt|lk)|tcl\-|tdg\-|tel(i|m)|tim\-|t\-mo|to(pl|sh)|ts(70|m\-|m3|m5)|tx\-9|up(\.b|g1|si)|utst|v400|v750|veri|vi(rg|te)|vk(40|5[0-3]|\-v)|vm40|voda|vulc|vx(52|53|60|61|70|80|81|83|85|98)|w3c(\-| )|webc|whit|wi(g |nc|nw)|wmlb|wonu|x700|yas\-|your|zeto|zte\-/i.test(a.substr(0,4))) check = true;})(navigator.userAgent||navigator.vendor||window.opera);

			return check;
		}

		/**
		 * Debounce the function call
		 *
		 * @param  {number}   threshold The delay.
		 * @param  {Function} callback  The function.
		 */
		debounce( threshold, callback ) {
			let timeout;

			return function debounced( $event ) {
				function delayed() {
					callback.call( this, $event );
					timeout = null;
				}

				if ( timeout ) {
					clearTimeout( timeout );
				}

				timeout = setTimeout( delayed, threshold );
			};
		}

		maybeTemplateLoad( templateId, templateContent, $templateContainer ) {

			if ( ! this.settings.megaAjaxLoad ) {
				return;
			}

			if ( $templateContainer.hasClass( 'template-loaded' ) ) {
				return;
			}

			let getMegaContentUrl = 'default' === templateContent ? window.jetMenuPublicSettings.getBlocksTemplateApiUrl : window.jetMenuPublicSettings.getElementorTemplateApiUrl;

			let signatures = this.settings['signatures'];
			let signature = '';

			if ( signatures.hasOwnProperty(`template_${templateId}`) ) {
				signature = signatures[`template_${templateId}`].signature;
			}

			$.ajax( {
				type: 'GET',
				url: getMegaContentUrl,
				dataType: 'json',
				data: {
					'id': templateId,
					'dev': window.jetMenuPublicSettings.devMode,
					'signature': signature
				},
				beforeSend: function( jqXHR, ajaxSettings ) {
					jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
				},
				success: function( responce, textStatus, jqXHR ) {
					const {content, contentElements} = responce;
					const templateData = {
						content,
						contentElements,
						contentType: templateContent,
					}

					$templateContainer.addClass( 'template-loaded' );

					jetMenu.megaContentRender( $( '.jet-mega-menu-mega-container__inner', $templateContainer ), templateData );
				}
			} );
		}
	}

	// jQuery plugin
	$.fn.JetMegaMenu = function( options ) {
		return this.each( function() {
			let $this         = $( this ),
				pluginOptions = ( 'object' === typeof options ) ? options : {};

			if ( ! $this.data( 'JetMegaMenu' ) ) {
				// create plugin instance (only if not exists) and expose the entire instance API
				$this.data( 'JetMegaMenu', new JetMegaMenuClass( this, pluginOptions ) );
			}
		} );
	};
} ( jQuery ));

// JetMenu Public Scripts
( function( $ ) {
	'use strict';

	window.jetMenu = {

		addedScripts: {},

		addedStyles: {},

		addedAssetsPromises: [],

		initedMobileRenderInstance: [],

		eventBus: new Vue(),

		$body: $( 'body' ),

		init: function() {
			this.initLocationMenuRender();
			this.mobileVueComponents();
			this.initMobileRender();

			window.addEventListener( 'jetMenu/editor/templateRenderer/renderSuccess', ( event ) => {
				this.initLocationMenuRender();
				this.mobileVueComponents();
				this.initMobileRender();
			}, false );

			$( window ).on( 'jet-menu/ajax/frontend-init', ( event, payload ) => {

				switch ( payload.contentType ) {
					case 'elementor':
						jetMenu.maybeElementorFrontendInit( payload.$container );
						break;
					case 'default':
						jetMenu.maybeDefaultFrontendInit( payload );
						break
				}
			} );

			$( window ).on( 'jet-menu/ajax/frontend-init/after', ( event, payload ) => {
				this.initLocationMenuRender();
				this.mobileVueComponents();
				this.initMobileRender();
				this.megaContentHandler(event, payload);

				if ( window.elementorFrontend ) {
					const elementorLazyLoad = new CustomEvent( "elementor/lazyload/observe" );
					document.dispatchEvent( elementorLazyLoad );
				}
			} );

			wp.hooks.addAction( 'jet-plugins.frontend.element-ready.jet-menu.mega-menu', 'jet-popup', ( $popupContainer, contentType ) => {
				this.initLocationMenuRender();
				this.mobileVueComponents();
				this.initMobileRender();
			} );

			// Init Vue for hamburger menu block in Gutenberg ( also on DOM change )
			if ( document.body.classList.contains( 'block-editor-page' ) ) {
				const tryObserve = () => {
					const target = document.querySelector( '.block-editor-block-list__layout' );

					if ( target ) {
						const initedMenus = new Set();

						const observer = new MutationObserver( () => {
							const menus = document.querySelectorAll( '.jet-mobile-menu--location-wp-nav' );

							menus.forEach( (menu) => {
								const menuId = menu.getAttribute( 'id' );

								if ( menuId && ! initedMenus.has( menuId ) ) {
									jetMenu.initMobileRender();
									initedMenus.add( menuId );
								}

							});
						});

						observer.observe( target, { childList: true, subtree: true } );
					} else {
						requestAnimationFrame( tryObserve );
					}
				};

				requestAnimationFrame( tryObserve );
			}

		},

		initLocationMenuRender: function() {

			let $megaMenuList = $( '.jet-mega-menu--location-wp-nav' );

			if ( ! $megaMenuList[0] ) {
				return false;
			}

			$megaMenuList.each( function() {
				let $this    = $( this ),
				    settings = $this.data( 'settings' );

				$this.JetMegaMenu( {
					rollUp: settings.rollUp,
					layout: settings.layout,
					subTrigger: settings.subTrigger,
					subEvent: settings.subEvent,
					subCloseBehavior: settings.subCloseBehavior,
					mouseLeaveDelay: settings.mouseLeaveDelay,
					breakpoint: settings.breakpoint,
					megaWidthType: settings.megaWidthType,
					megaWidthSelector: settings.megaWidthSelector,
					megaAjaxLoad: settings.megaAjaxLoad,
					classes: {
						instance: 'jet-mega-menu',
						menuContainer: 'jet-mega-menu-container',
						menuList: 'jet-mega-menu-list',
						menuItem: 'jet-mega-menu-item',
						menuItemLink: 'jet-mega-menu-item__link',
						subMenuContainer: 'jet-mega-menu-sub-menu',
						subMenuList: 'jet-mega-menu-sub-menu__list',
						megaContainer: 'jet-mega-menu-mega-container',
					}
				} );
			} );
		},

		megaContentHandler: function(event, payload) {
			const container = payload.$container[0];
			const mobileMenu = container.closest('.jet-mobile-menu');

			if ( ! mobileMenu ) {
				return;
			}

			const { menuOptions } = mobileMenu.dataset;
			const { menuUniqId } = JSON.parse( menuOptions );

			container.addEventListener('click', function (event) {
				const link = event.target.closest('a');

				if (!link) {
					return;
				}

				if (link.getAttribute('href')[0] !== '#') {
					return;
				}

				window.jetMenu.eventBus.$emit('closeMenu', {
					menuUniqId: menuUniqId,
				});
			});
		},

		initMobileRender: function() {

			let mobileMenuList = $( '.jet-mobile-menu--location-wp-nav' );

			if ( ! mobileMenuList[0] ) {
				return false;
			}

			if ( 'true' === window.jetMenuPublicSettings.devMode ) {
				Vue.config.devtools = true;
			}

			mobileMenuList.each( function() {
				let $this          = $( this ),
					menuInstanceId = $this.attr( 'id' ),
					menuId         = $this.data( 'menu-id' ) || false,
					menuOptions    = $this.data( 'menu-options' ) || {};

				jetMenu.createMobileRenderInstance( menuInstanceId, menuId, menuOptions );
			} );
		},

		createMobileRenderInstance: function( menuInstanceId, menuId, menuOptions ) {

			if ( jetMenu.initedMobileRenderInstance.includes( menuInstanceId ) ) {
				return;
			}

			jetMenu.initedMobileRenderInstance.push( menuInstanceId );

			let mobileRenderInstance = new Vue( {
				el: '#' + menuInstanceId,
				data: {
					uniqId: menuInstanceId,
					menuOptions: menuOptions,
					refsHtml: {},
				},
				mounted: function() {
					let refsHtml = {};

					for ( var ref in this.$refs ) {
						Object.assign( refsHtml, { [ ref ]: this.$refs[ ref ].innerHTML } );
					}

					this.refsHtml = refsHtml;
				}
			} );
		},

		mobileVueComponents: function() {

			Vue.component( 'mobile-menu-item', {
				template: '#mobile-menu-item-template',

				props: {
					itemDataObject: Object,
					depth: Number
				},

				data: function() {
					return ( {
						ajaxRequest: null,
						templateLoadStatus: false,
						subDropdownVisible: false
					} )
				},

				computed: {

					itemClasses: function() {
						let itemClasses = [
							'jet-mobile-menu__item',
							'jet-menu-item-' + this.itemDataObject.itemId,
							'jet-mobile-menu__item--sub-trigger-' + ( this.$root.menuOptions.subTrigger || 'item' ),
						];

						let customClasses = this.itemDataObject.classes;

						if ( 0 !== customClasses.length ) {
							itemClasses = itemClasses.concat( customClasses );
						}

						const { href } = window.location;
						let pageURL = null;

						if ( href.includes('?') ) {
							pageURL = href.substring(0, href.indexOf('?'));
						} else {
							pageURL = href;
						}

						if ( pageURL === this.itemDataObject.url ) {
							itemClasses.push( 'jet-mobile-menu__item--active' );
						}

						return itemClasses;
					},

					itemLinkClasses: function() {
						let classes = [
							'mobile-link',
							0 === this.depth ? 'mobile-top-level-link' : 'mobile-sub-level-link',
						];

						return classes;
					},

					isСhildrenDefine: function() {
						return this.itemDataObject.children ? true : false;
					},

					isTemplateDefine: function() {
						return false !== this.itemDataObject.megaTemplateId ? true : false;
					},

					megaContentType: function() {
						return this.itemDataObject.megaContentType;
					},

					isAjaxLoadingEnabled: function() {
						return this.$root.menuOptions.megaAjaxLoad === true;
					},

					getTemplateUrl: function() {
						return 'default' === this.megaContentType ? window.jetMenuPublicSettings.getBlocksTemplateApiUrl : window.jetMenuPublicSettings.getElementorTemplateApiUrl;
					},

					isSub: function() {
						return this.isСhildrenDefine || this.isTemplateDefine ? true : false;
					},

					isTopLevel: function() {
						return 0 === this.depth ? true : false;
					},

					isDropdownLayout: function() {
						return this.isSub && ! this.isTemplateDefine && 'dropdown' === this.$root.menuOptions.subOpenLayout;
					},

					depthClass: function() {
						return 0 === this.depth ? 'mobile-top-level-link' : 'mobile-sub-level-link';
					},

					dropdownIconHtml: function() {
						let dropdownIcon = this.$root.refsHtml.dropdownIcon ? this.$root.refsHtml.dropdownIcon : '<span class="dashicons dashicons-arrow-right"></span>',
							dropdownOpenedIcon = this.$root.refsHtml.dropdownOpenedIcon ? this.$root.refsHtml.dropdownOpenedIcon : '<span class="dashicons dashicons-arrow-down"></span>';

						if ( this.subDropdownVisible ) {
							dropdownIcon = dropdownOpenedIcon;
						}

						return dropdownIcon;
					},

					itemIconHtml: function() {
						return this.itemDataObject.itemIcon;
					},

					isIconVisible: function() {
						let iconVisible = this.$root.menuOptions.itemIconVisible;

						return ! iconVisible || '' === this.itemDataObject.itemIcon || ! this.itemDataObject.itemIcon ? false : true;
					},

					isBadgeVisible: function() {
						let badgeVisible = this.$root.menuOptions.itemBadgeVisible;

						return false === badgeVisible || '' === this.itemDataObject.badgeContent || ! this.itemDataObject.badgeContent ? false : true;
					},

					isLabelVisible: function() {
						let labelVisible = ! this.itemDataObject.hideItemText;

						return false === labelVisible || '' === this.itemDataObject.name || ! this.itemDataObject.name ? false : true;
					},

					isDescVisible: function() {
						let descVisible = this.$root.menuOptions.itemDescVisible;

						return false === descVisible || '' === this.itemDataObject.description || ! this.itemDataObject.description ? false : true;
					},

					loaderColor: function() {
						return this.$root.menuOptions.loaderColor || '#3a3a3a';
					},
				},

				methods: {
					itemSubHandler: function( event ) {
						let target     = event.target,
							mobileLink = $( target ).closest( '.mobile-link' );

						if ( 'item' !== this.$root.menuOptions.subTrigger ) {
							return;
						}

						if ( this.isSub && mobileLink ) {
							event.preventDefault();
						}

						if ( ! this.isSub && mobileLink && this.$root.menuOptions.closeAfterNavigate ) {
							jetMenu.eventBus.$emit( 'closeMenu', {
								menuUniqId: this.$root.menuOptions.menuUniqId,
							} );
						}

						this.switchToSub( event );
					},

					markerSubHandler: function( event ) {

						if ( 'submarker' !== this.$root.menuOptions.subTrigger ) {
							return;
						}

						this.switchToSub( event );
					},

					switchToSub: function( event ) {

						if ( ! this.isSub ) {
							return;
						}

						if ( ! this.isTemplateDefine ) {

							if ( this.isDropdownLayout ) {
								this.subDropdownVisible = !this.subDropdownVisible;

								return;
							}

							jetMenu.eventBus.$emit( 'itemsSubSwitch', {
								menuUniqId: this.$root.menuOptions.menuUniqId,
								id: this.itemDataObject.id,
								name: this.itemDataObject.name,
								children: this.itemDataObject.children || false
							} );
						} else {
							if ( this.isAjaxLoadingEnabled && ! this.itemDataObject.megaContentLoaded ) {
								this.getMegaTemplate();
							} else {
								jetMenu.eventBus.$emit( 'showTemplateContent', {
									menuUniqId: this.$root.menuOptions.menuUniqId,
									id: this.itemDataObject.id,
									name: this.itemDataObject.name,
									megaContent: this.itemDataObject.megaContent,
									megaContentType: this.itemDataObject.megaContentType,
								} );
							}
						}
					},

					getMegaTemplate: function() {
						var vueInstance = this;

						if ( ! this.isAjaxLoadingEnabled ) {
							return;
						}

						var signature = vueInstance.itemDataObject.signature || '';

						vueInstance.ajaxRequest = $.ajax( {
							type: 'GET',
							url: vueInstance.getTemplateUrl,
							dataType: 'json',
							data: {
								'id': vueInstance.itemDataObject.megaTemplateId,
								'dev': window.jetMenuPublicSettings.devMode,
								'signature': signature
							},
							beforeSend: function( jqXHR, ajaxSettings ) {

								if ( null !== vueInstance.ajaxRequest ) {
									vueInstance.ajaxRequest.abort();
								}

								vueInstance.templateLoadStatus = true;

								jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
							},
							success: function( responce, textStatus, jqXHR ) {
								let templateContent = responce['content'],
									contentElements = responce['contentElements'];

								vueInstance.templateLoadStatus = false;
								vueInstance.itemDataObject.megaContent = templateContent;
								vueInstance.itemDataObject.megaContentLoaded = true;

								jetMenu.eventBus.$emit( 'showTemplateContent', {
									menuUniqId: vueInstance.$root.menuOptions.menuUniqId,
									id: vueInstance.itemDataObject.id,
									name: vueInstance.itemDataObject.name,
									megaContent: vueInstance.itemDataObject.megaContent,
									megaContentType: vueInstance.itemDataObject.megaContentType,
								} );
							}
						} );
					}
				}

			});

			Vue.component( 'mobile-menu-list', {
				template: '#mobile-menu-list-template',
				props: {
					depth: Number,
					childrenObject: Object
				}
			} );

			Vue.component( 'mobile-menu', {
				template: '#mobile-menu-template',

				data: function() {
					return ( {
						menuOpen: false,
						children: false,
						itemsRawData: {},
						trail:[],
						breadcrumbsData: [],
						animation: 'items-next-animation',
						ajaxRequest: null,
						templateVisible: false,
						instanceLoadStatus: false,
						itemTemplateContent: false,
						headerTemplate: this.$root.menuOptions['headerTemplate'] || 0,
						headerContent: false,
						beforeTemplate: this.$root.menuOptions['beforeTemplate'] || 0,
						beforeContent: false,
						afterTemplate: this.$root.menuOptions['afterTemplate'] || 0,
						afterContent: false,
						ajaxPromises: [],
					} )
				},

				mounted: function() {
					const vueInstance = this;

					if ( this.menuOpen ) {
						jetMenu.$body.addClass( 'jet-mobile-menu-visible' );

						if ( 'slide-out' === this.$root.menuOptions.menuLayout ) {
							jetMenu.$body.addClass( 'jet-menu-body-blocker' );
						}
					}

					let menuInstanceRenderData = false,
						renderDataElement = document.getElementById( 'jetMenuMobileWidgetRenderData' + this.$root.menuOptions.menuUniqId );

					try {
						menuInstanceRenderData = JSON.parse( renderDataElement.textContent );
					} catch ( error ) {
						menuInstanceRenderData = false;
					}

					if ( menuInstanceRenderData ) {
						this.itemsRawData = menuInstanceRenderData['items'];

						const headerTemplateData = menuInstanceRenderData.headerTemplateData || false,
							beforeTemplateData = menuInstanceRenderData.beforeTemplateData || false,
							afterTemplateData = menuInstanceRenderData.afterTemplateData || false;

						if ( headerTemplateData ) {
							this.headerContent = headerTemplateData.content;
						}

						if ( beforeTemplateData ) {
							this.beforeContent = beforeTemplateData.content;
						}

						if ( afterTemplateData ) {
							this.afterContent = afterTemplateData.content;
						}
					} else {
						this.ajaxPromises.push(
							new Promise( function( resolve, reject ) {

								$.ajax( {
									type: 'GET',
									url: window.jetMenuPublicSettings.menuItemsApiUrl,
									dataType: 'json',
									data: {
										'menu_id': vueInstance.menuId,
										'dev': window.jetMenuPublicSettings.devMode,
										'lang': window.jetMenuPublicSettings.wpmlLanguageCode || false
									},
									beforeSend: function( jqXHR, ajaxSettings ) {
										jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
									},
									success: function( responce, textStatus, jqXHR ) {
										let responceData = responce.data.items;

										vueInstance.itemsRawData = responceData;

										resolve();
									}
								} );
							} )
						);

						if ( 0 !== +this.headerTemplate ) {
							this.ajaxPromises.push(
								new Promise( function( resolve, reject ) {
									$.ajax( {
										type: 'GET',
										url: window.jetMenuPublicSettings.getElementorTemplateApiUrl,
										dataType: 'json',
										data: {
											'id': vueInstance.headerTemplate,
											'dev': window.jetMenuPublicSettings.devMode,
											'nocache': new Date().getTime(),
										},
										beforeSend: function( jqXHR, ajaxSettings ) {
											jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
										},
										success: function( responce, textStatus, jqXHR ) {
											let templateContent = responce['content'],
												templateScripts = responce['scripts'],
												templateStyles  = responce['styles'];

											for ( let scriptHandler in templateScripts ) {
												jetMenu.addedAssetsPromises.push( jetMenu.loadScriptAsync( scriptHandler, templateScripts[ scriptHandler ] ) );
											}

											for ( let styleHandler in templateStyles ) {
												jetMenu.addedAssetsPromises.push( jetMenu.loadStyle( styleHandler, templateStyles[ styleHandler ] ) );
											}

											vueInstance.headerContent = templateContent;

											resolve();
										}
									} );
								} )
							);
						}

						if ( 0 !== +this.beforeTemplate ) {
                            this.ajaxPromises.push(
                                new Promise( function( resolve, reject ) {
                                    $.ajax( {
                                        type: 'GET',
                                        url: window.jetMenuPublicSettings.getElementorTemplateApiUrl,
                                        dataType: 'json',
                                        data: {
                                            'id': vueInstance.beforeTemplate,
                                            'dev': window.jetMenuPublicSettings.devMode,
                                            'nocache': new Date().getTime(),
                                        },
                                        beforeSend: function( jqXHR, ajaxSettings ) {
                                            jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
                                        },
                                        success: function( responce, textStatus, jqXHR ) {
                                            let templateContent = responce['content'],
                                                templateScripts = responce['scripts'],
                                                templateStyles  = responce['styles'];

                                            for ( let scriptHandler in templateScripts ) {
                                                jetMenu.addedAssetsPromises.push( jetMenu.loadScriptAsync( scriptHandler, templateScripts[ scriptHandler ] ) );
                                            }

                                            for ( let styleHandler in templateStyles ) {
                                                jetMenu.addedAssetsPromises.push( jetMenu.loadStyle( styleHandler, templateStyles[ styleHandler ] ) );
                                            }

                                            vueInstance.beforeContent = templateContent;

                                            resolve();
                                        }
                                    } );
                                } )
                            );
                        }

                        if ( 0 !== +this.afterTemplate ) {
                            this.ajaxPromises.push(
                                new Promise( function( resolve, reject ) {
                                    $.ajax( {
                                        type: 'GET',
                                        url: window.jetMenuPublicSettings.getElementorTemplateApiUrl,
                                        dataType: 'json',
                                        data: {
                                            'id': vueInstance.afterTemplate,
                                            'dev': window.jetMenuPublicSettings.devMode,
                                            'nocache': new Date().getTime(),
                                        },
                                        beforeSend: function( jqXHR, ajaxSettings ) {
                                            jqXHR.setRequestHeader( 'X-WP-Nonce', window.jetMenuPublicSettings.restNonce );
                                        },
                                        success: function( responce, textStatus, jqXHR ) {
                                            let templateContent = responce['content'],
                                                templateScripts = responce['scripts'],
                                                templateStyles  = responce['styles'];

                                            for ( let scriptHandler in templateScripts ) {
                                                jetMenu.addedAssetsPromises.push( jetMenu.loadScriptAsync( scriptHandler, templateScripts[ scriptHandler ] ) );
                                            }

                                            for ( let styleHandler in templateStyles ) {
                                                jetMenu.addedAssetsPromises.push( jetMenu.loadStyle( styleHandler, templateStyles[ styleHandler ] ) );
                                            }

                                            vueInstance.afterContent = templateContent;
                                            resolve();
                                        }
                                    } );
                                } )
                            );
                        }
					}



					this.instanceLoadStatus = true;

					Promise.all( this.ajaxPromises ).then( function() {
						vueInstance.instanceLoadStatus = false;
						//vueInstance.initTemplatesContent();
					}, function( reason ) {
						console.log( 'Script Loaded Error' );
					} );

					jetMenu.eventBus.$on( 'itemsSubSwitch', function ( payLoad ) {

						if ( vueInstance.$root.menuOptions.menuUniqId !== payLoad.menuUniqId ) {
							return;
						}

						vueInstance.trail.push( payLoad.children );
						vueInstance.children = payLoad.children;
						vueInstance.animation = 'items-next-animation';
						vueInstance.breadcrumbsData.push( payLoad.name );
					} );

					jetMenu.eventBus.$on( 'showTemplateContent', function ( payLoad ) {

						if ( vueInstance.$root.menuOptions.menuUniqId !== payLoad.menuUniqId ) {
							return;
						}

						vueInstance.itemTemplateContent = payLoad.megaContent.content;
						vueInstance.templateVisible = true;
						vueInstance.breadcrumbsData.push( payLoad.name );
						vueInstance.animation = 'items-next-animation';

						const templateData = {
							content: payLoad.megaContent.content !== undefined
								? payLoad.megaContent.content
								: payLoad.megaContent,
							contentElements: payLoad.megaContent.contentElements,
							contentType: payLoad.megaContentType,
						}

						vueInstance.showTemplateContent( templateData );
					} );

					jetMenu.eventBus.$on( 'closeMenu', function( payLoad ) {

						if ( vueInstance.$root.menuOptions.menuUniqId !== payLoad.menuUniqId ) {
							return;
						}

						vueInstance.closeMenu();
					} );

				},

				watch: {
					menuOpen: function( curr, prev ) {

						if ( curr ) {
							jetMenu.$body.addClass( 'jet-mobile-menu-visible' );

							if ( 'slide-out' === this.$root.menuOptions.menuLayout ) {
								jetMenu.$body.addClass( 'jet-menu-body-blocker' );
							}

							this.initTemplatesContent();
						}

						if ( ! curr ) {
							jetMenu.$body.removeClass( 'jet-mobile-menu-visible' );

							if ( 'slide-out' === this.$root.menuOptions.menuLayout ) {
								jetMenu.$body.removeClass( 'jet-menu-body-blocker' );
							}

							this.clearStates();
						}
					}
				},

				computed: {
					instanceClass: function() {

						let classes = [
							'jet-mobile-menu__instance',
							'jet-mobile-menu__instance--' + this.$root.menuOptions.menuLayout + '-layout',
							this.$root.menuOptions.menuPosition + '-container-position',
							( this.$root.menuOptions.togglePosition || 'default' ) + '-toggle-position',
							this.$root.menuOptions.fillSvgIcon ? 'fill-svg-icon' : '',
						];

						return classes;
					},

					menuContainerVisible: function() {
						return this.menuOpen && !this.instanceLoadStatus;
					},

					menuId: function() {

						if ( this.$root.menuOptions.mobileMenuId && window.jetMenuPublicSettings.isMobile === 'true' ) {
							return this.$root.menuOptions.mobileMenuId;
						}

						return this.$root.menuOptions.menuId;
					},

					coverVisible: function() {

						let avaliableForLayout = [
							'slide-out'
						];

						return avaliableForLayout.includes( this.$root.menuOptions.menuLayout );
					},

					itemsList: function() {

						if ( ! this.children ) {
							return this.itemsRawData;
						}

						return this.children;
					},

					isClose: function() {
						let avaliableForLayout = [
							'slide-out'
						];

						return avaliableForLayout.includes( this.$root.menuOptions.menuLayout );
					},

					isBack: function() {
						return this.children || this.templateVisible ? true : false;
					},

					isBreadcrumbs: function() {
						return this.$root.menuOptions.useBreadcrumb && 0 !== this.breadcrumbsData.length ? true : false;
					},

					breadcrumbsPathData: function() {

						if ( 'minimal' === this.$root.$root.menuOptions.breadcrumbPath && 1 < this.breadcrumbsData.length ) {
							return this.breadcrumbsData.filter( ( item, index, breadcrumbsData ) => {
								return 	index === breadcrumbsData.length - 1;
							} );
						}

						return this.breadcrumbsData;
					},

					depth: function() {
						return this.trail.length;
					},

					containerPosition: function() {
						return this.$root.menuOptions.menuPosition;
					},

					showAnimation: function() {

						let animation = false;

						switch( this.$root.menuOptions.menuLayout ) {

							case 'slide-out':
								animation = 'right' === this.containerPosition ? 'menu-container-left-animation' : 'menu-container-right-animation';
								break;

							case 'dropdown':
								animation = 'menu-container-dropdown-animation';
								break;

							case 'push':
								animation = 'menu-container-expand-animation';
								break;
						}

						return animation;
					},

					toggleClosedIcon: function() {
						return this.$root.refsHtml.toggleClosedIcon || '';
					},

					toggleOpenedIcon: function() {
						return this.$root.refsHtml.toggleOpenedIcon || '';
					},

					toggleText: function() {
						return '' !== this.$root.menuOptions.toggleText ? this.$root.menuOptions.toggleText : false;
					},

					closeIcon: function() {
						return this.$root.refsHtml.closeIcon || '';
					},

					backIcon: function() {
						let backIcon = this.$root.refsHtml.backIcon || '',
							backText = '' !== this.$root.menuOptions.backText ? '<span>' + this.$root.menuOptions.backText + '</span>' : '',
							backHtml = backIcon + backText;

						return backHtml;
					},

					backText: function() {
						return '' !== this.$root.menuOptions.backText ? this.$root.menuOptions.backText : false;
					},

					breadcrumbIcon: function() {
						return this.$root.refsHtml.breadcrumbIcon || '';
					},

					loaderColor: function() {
						return this.$root.menuOptions.loaderColor || '#3a3a3a';
					},

					toggleLoaderVisible: function() {
						return this.$root.menuOptions.toggleLoader && this.instanceLoadStatus && this.menuOpen ? true : false;
					},

					headerTemplateVisible: function() {
						return this.headerContent ? true : false;
					},

					beforeTemplateVisible: function() {
						return this.beforeContent ? true : false;
					},

					afterTemplateVisible: function() {
						return this.afterContent ? true : false;
					}

				},

				methods: {
					menuToggle: function() {
						this.menuOpen = ! this.menuOpen;
					},

					closeMenu: function() {
						this.menuOpen = false;
					},

					clearStates: function() {
						this.trail = [];
						this.children = false;
						this.breadcrumbsData = [];
						this.templateVisible = false;
					},

					goBack: function() {

						this.animation = 'items-prev-animation';

						if ( ! this.templateVisible ) {
							this.$delete( this.trail, this.trail.length - 1 );
							this.children = this.trail.slice(-1)[0] || false;
						} else {
							this.templateVisible = false;
						}

						this.$delete(this.breadcrumbsData, this.breadcrumbsData.length - 1);
					},

					escapeKeyHandler: function() {

						if ( this.isBack ) {
							this.goBack();
						} else {
							this.closeMenu();
						}
					},

					showTemplateContent: function( templateData = {} ) {
						let vueInstance = this;

						this.$nextTick( function() {
							let $templateContainer = $( vueInstance.$refs['template-content'] ).find( '.jet-mobile-menu__template-content' );

							jetMenu.megaContentRender( $templateContainer, templateData );
						} );
					},

					initTemplatesContent: function() {
						let vueInstance = this;

						this.$nextTick( function() {

							if ( vueInstance.headerContent ) {
								let $headerContainer = $( vueInstance.$refs['header-template-content'] );

								jetMenu.megaContentRender( $headerContainer, { contentType: 'elementor' } );
							}

							if ( vueInstance.beforeContent ) {
								let $beforeContainer = $( vueInstance.$refs['before-template-content'] );

								jetMenu.megaContentRender( $beforeContainer, { contentType: 'elementor' } );
							}

							if ( vueInstance.afterContent ) {
								let $afterContainer = $( vueInstance.$refs['after-template-content'] );

								jetMenu.megaContentRender( $afterContainer, { contentType: 'elementor' } );
							}
						} );
					},

					breadcrumbHandle: function( index ) {

						if ( index === this.breadcrumbsData.length ) {
							return;
						}

						if ( 'minimal' === this.$root.menuOptions.breadcrumbPath ) {
							this.goBack();

							return;
						}

						this.animation = 'items-prev-animation';
						this.trail = this.trail.slice( 0, index );
						this.children = this.trail.slice( -1 )[0] || false;
						this.templateVisible = false;
						this.breadcrumbsData = this.breadcrumbsData.slice( 0, index );
					}

				}
			});
		},

		loadScriptAsync: function( script, uri ) {

			if ( jetMenu.addedScripts.hasOwnProperty( script ) ) {
				return script;
			}

			jetMenu.addedScripts[ script ] = uri;

			return new Promise( function( resolve, reject ) {
				var tag = document.createElement( 'script' );

					tag.src    = uri;
					tag.async  = true;
					tag.onload = function() {
						resolve( script );
					};

				document.head.appendChild( tag );
			} );
		},

		loadStyle: function( style, uri ) {

			if ( jetMenu.addedStyles.hasOwnProperty( style ) && jetMenu.addedStyles[ style ] ===  uri) {
				return style;
			}

			jetMenu.addedStyles[ style ] = uri;

			return new Promise( function( resolve, reject ) {
				var tag = document.createElement( 'link' );

					tag.id      = style;
					tag.rel     = 'stylesheet';
					tag.href    = uri;
					tag.type    = 'text/css';
					tag.media   = 'all';
					tag.onload  = function() {
						resolve( style );
					};

				document.head.appendChild( tag );
			});
		},

		megaContentRender: function( $templateContainer, templateData = {} ) {

			if ( templateData.content ) {
				$templateContainer.html( templateData.content );
			}

			const data = {
				$container: $templateContainer,
				...templateData
			}

			Promise.all( jetMenu.addedAssetsPromises ).then( function( value ) {
				// Before ajax frontend init
				$( window ).trigger( 'jet-menu/ajax/frontend-init/before', data );

				// Frontend init
				$( window ).trigger( 'jet-menu/ajax/frontend-init', data );

				// after ajax frontend init
				$( window ).trigger( 'jet-menu/ajax/frontend-init/after', data );
			}, function( reason ) {
				console.log( 'Script Loaded Error' );
			});
		},

		maybeElementorFrontendInit: function( $templateContainer ) {

			$templateContainer.find( 'div[data-element_type]' ).each( function() {
				var $this       = $( this ),
					elementType = $this.data( 'element_type' );

				if ( ! elementType ) {
					return;
				}

				try {
					if ( 'widget' === elementType ) {
						elementType = $this.data( 'widget_type' );

						if ( window.elementorFrontend && window.elementorFrontend.hooks ) {
							window.elementorFrontend.hooks.doAction( 'frontend/element_ready/widget', $this, $ );
						}
					}

					if ( window.elementorFrontend && window.elementorFrontend.hooks ) {
						window.elementorFrontend.hooks.doAction( 'frontend/element_ready/global', $this, $ );
						window.elementorFrontend.hooks.doAction( 'frontend/element_ready/' + elementType, $this, $ );
					}

				} catch ( err ) {
					console.log(err);
					$this.remove();

					return false;
				}
			} );
		},

		maybeDefaultFrontendInit: function ( payload ) {
			const contentElements = payload.contentElements || [],
				$container = payload.$container;

			$container.find( '[data-is-block*="/"]' ).each( ( index, el ) => {
				window.JetPlugins.hooks.doAction( window.JetPlugins.hookNameFromBlock( el.dataset.isBlock ), jQuery( el ) );
			} );
		},

		getUniqId: function() {
			return Math.random().toString( 36 ).substr( 2, 9 );
		},

	};

	jetMenu.init();

} ( jQuery ) );

