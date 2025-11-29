( function( $, elementor ) {

	"use strict";

	var JetMenuWidget = {

		init: function() {

			var widgets = {
				'jet-mega-menu.default' : JetMenuWidget.widgetMegaMenu,
				'jet-custom-menu.default' : JetMenuWidget.widgetCustomMenu,
				'jet-mobile-menu.default' : JetMenuWidget.widgetMobileMenu,
			};

			$.each( widgets, function( widget, callback ) {
				elementor.hooks.addAction( 'frontend/element_ready/' + widget, callback );
			} );

		},

		widgetMegaMenu: function( $scope ) {
			let $megaMenu   = $scope.find( '.jet-mega-menu--location-elementor' ),
			    $mobileMenu = $scope.find( '.jet-mobile-menu' );

			if ( JetMenuWidget.shouldSetIpadProCookie() ) {
				document.cookie = "is_ipad_pro=true; path=/";
				location.reload();
				return;
			}

			if ( $megaMenu[0] ) {
				let settings = $megaMenu.data( 'settings' );

				$megaMenu.JetMegaMenu( {
					menuId: settings.menuId,
					menuUniqId: settings.menuUniqId,
					rollUp: settings.rollUp,
					layout: settings.layout,
					subEvent: settings.subEvent,
					subCloseBehavior: settings.subCloseBehavior,
					mouseLeaveDelay: settings.mouseLeaveDelay,
					subTrigger: settings.subTrigger,
					breakpoint: settings.breakpoint,
					megaWidthType: settings.megaWidthType,
					megaWidthSelector: settings.megaWidthSelector,
					megaAjaxLoad: settings.megaAjaxLoad,
					signatures: settings.signatures,
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

				requestAnimationFrame(() => {
					window.dispatchEvent( new Event( 'resize' ) );
				});

			}

			if ( $mobileMenu[0] ) {
				let menuInstanceId = $mobileMenu.attr( 'id' ),
				    menuId         = $mobileMenu.data( 'menu-id' ) || false,
				    menuOptions    = $mobileMenu.data( 'menu-options' ) || {};

				window.jetMenu.createMobileRenderInstance( menuInstanceId, menuId, menuOptions );
			}
		},

		widgetCustomMenu: function( $scope ) {
			var $target = $scope.find( '.jet-custom-nav' ),
				instance = null,
				trigger = $target.data( 'trigger' ),
				targetType = trigger === 'click' ? $target.data( 'target' ) || 'item' : null,
				menuItem = null,
				menuItemSelector = trigger === 'click' && targetType === 'sub_icon'
					? '.jet-dropdown-arrow'
					: '.jet-custom-nav__item > a';

			if ( ! $target.length ) {
				return;
			}

			if ( JetMenuWidget.mobileAndTabletcheck() ) {
				$scope.on( 'touchstart', '.jet-custom-nav__item > a, .jet-custom-nav__item > a .jet-dropdown-arrow', touchStartItem );
				$scope.on( 'touchend', '.jet-custom-nav__item > a, .jet-custom-nav__item > a .jet-dropdown-arrow', touchEndItem );
			} else {
				if ( trigger === 'click' ) {
					$scope.on( 'click', menuItemSelector, toggleSubMenu );
					$scope.on( 'mouseleave', '.jet-custom-nav__item', mouseLeaveHandler );
				} else {
					$scope.on( 'mouseenter mouseover', '.jet-custom-nav__item', mouseEnterHandler );
					$scope.on( 'mouseleave', '.jet-custom-nav__item', mouseLeaveHandler );
				}
			}

			function toggleSubMenu( event ) {
				const $this = $( event.currentTarget ).closest( '.jet-custom-nav__item' );

				if ( ! $this.hasClass( 'menu-item-has-children' ) ) {
					return;
				}

				event.preventDefault();
				event.stopPropagation();

				const isOpen = $this.hasClass( 'hover-state' );

				if ( $this.hasClass( 'hover-state' ) ) {
					$this.removeClass( 'hover-state' );
				} else {
					$this.addClass( 'hover-state' );
					$this.siblings().removeClass( 'hover-state' );
				}

				if ( $this.is( '[aria-haspopup="true"]' ) ) {
					$this.attr( 'aria-expanded', isOpen ? 'false' : 'true' );
				}

				$this.find('.jet-dropdown-arrow[aria-haspopup="true"]').attr('aria-expanded', isOpen ? 'false' : 'true');
			}

			function mouseEnterHandler( event ) {
				menuItem = $( event.target ).parents( '.jet-custom-nav__item' );

				if ( menuItem.is( '[aria-haspopup="true"]' ) ) {
					menuItem.attr( 'aria-expanded', 'true' );
				}

				menuItem.addClass( 'hover-state' );
			}

			function mouseLeaveHandler( event ) {
				const $this = $( event.currentTarget ).closest( '.jet-custom-nav__item' );
				const relatedTarget = event.relatedTarget;

				if ( $this.has( relatedTarget ).length > 0 ) {
					return;
				}

				menuItem = $this;
				menuItem.removeClass( 'hover-state' );

				if ( $this.is( '[aria-haspopup="true"]' ) ) {
					$this.attr( 'aria-expanded', 'false' );
				}

				$this.find( '.jet-dropdown-arrow[aria-haspopup="true"]' ).attr( 'aria-expanded', 'false' );
			}

			function touchStartItem( event ) {
				var $this = $( event.currentTarget ).closest( '.jet-custom-nav__item' );

				$this.data( 'offset', $this.offset().top );
				$this.data( 'windowOffset', $( window ).scrollTop() );
			}

			function touchEndItem( event ) {
				var $currentTarget,
					$this,
					$siblingsItems,
					$link,
					linkHref,
					subMenu,
					offset,
					windowOffset;

				event.preventDefault();
				event.stopPropagation();

				$currentTarget = $( event.currentTarget );
				$this          = $currentTarget.closest( '.jet-custom-nav__item' );
				$siblingsItems = $this.siblings( '.jet-custom-nav__item.menu-item-has-children' );
				$link          = $( '> a', $this );
				linkHref       = $link.attr( 'href' );
				subMenu        = $( '.jet-custom-nav__sub:first, .jet-custom-nav__mega-sub:first', $this );
				offset         = $this.data( 'offset' );
				windowOffset   = $this.data( 'windowOffset' );

				if ( offset !== $this.offset().top || windowOffset !== $( window ).scrollTop() ) {
					return false;
				}

				if ( $currentTarget.hasClass( 'jet-dropdown-arrow' ) ) {

					if ( !subMenu[0] ) {
						return false;
					}

					const isOpen = $this.hasClass( 'hover-state' );

					if ( ! $this.hasClass( 'hover-state' ) ) {
						$this.addClass( 'hover-state' );

						$siblingsItems.removeClass( 'hover-state' ).each( function() {
							const $sibling = $( this );

							if ( $sibling.is( '[aria-haspopup="true"]' ) ) {
								$sibling.attr( 'aria-expanded', 'false' );
							}

							$sibling.find('> a > .jet-dropdown-arrow[aria-haspopup="true"]').attr( 'aria-expanded', 'false' );
						} );

						$siblingsItems.removeClass( 'hover-state' );
						$( '.jet-custom-nav__item.menu-item-has-children', $siblingsItems ).removeClass( 'hover-state' );
					} else {
						$this.removeClass( 'hover-state' );

						$( '.jet-custom-nav__item.menu-item-has-children', $this ).removeClass( 'hover-state' );
					}

					if ( $this.is( '[aria-haspopup="true"]' ) ) {
						$this.attr( 'aria-expanded', isOpen ? 'false' : 'true' );
					}

					$this.find( '> a > .jet-dropdown-arrow[aria-haspopup="true"]' ).attr( 'aria-expanded', isOpen ? 'false' : 'true' );

				}

				if ( $currentTarget.hasClass( 'jet-custom-nav__item-link' ) ) {

					if ( '#' === linkHref ) {
						if ( ! $this.hasClass( 'hover-state' ) ) {
							$this.addClass( 'hover-state' );

							$siblingsItems.removeClass( 'hover-state' );
							$( '.jet-custom-nav__item.menu-item-has-children', $siblingsItems ).removeClass( 'hover-state' );
						} else {
							$this.removeClass( 'hover-state' );

							$( '.jet-custom-nav__item.menu-item-has-children', $this ).removeClass( 'hover-state' );
						}
					} else {

						window.location = linkHref;

						return false;
					}

				}
			}

			var initSubMenuPosition = false;

			function setSubMenuPosition(){
				if ( initSubMenuPosition ) {
					$target.find( '.jet-custom-nav__sub.inverse-side' ).removeClass( 'inverse-side' );
					initSubMenuPosition = false;
				}

				var subMenu  = $( '.jet-custom-nav__sub', $target ),
					$body    = $( 'body' ),
					maxWidth = $body.outerWidth( true ),
					isMobile = 'mobile' === elementor.getCurrentDeviceMode();

				if ( isMobile ) {
					return;
				}

				if ( subMenu[0] ) {
					subMenu.each( function() {
						var $this = $( this ),
							subMenuOffsetLeft = $this.offset().left,
							subMenuOffsetRight = subMenuOffsetLeft + $this.outerWidth( true ),
							subMenuPosition = $this.closest( '.jet-custom-nav' ).hasClass( 'jet-custom-nav--dropdown-left-side' ) ? 'left-side' : 'right-side';

						if ( 'right-side' === subMenuPosition ) {
							if ( subMenuOffsetRight >= maxWidth ) {
								$this.addClass( 'inverse-side' );
								$this.find( '.jet-custom-nav__sub' ).addClass( 'inverse-side' );

								initSubMenuPosition = true;
							} else if ( subMenuOffsetLeft < 0 ) {
								$this.removeClass( 'inverse-side' );
								$this.find( '.jet-custom-nav__sub' ).removeClass( 'inverse-side' );
							}
						} else {
							if ( subMenuOffsetLeft < 0 ) {
								$this.addClass( 'inverse-side' );
								$this.find( '.jet-custom-nav__sub' ).addClass( 'inverse-side' );

								initSubMenuPosition = true;
							} else if ( subMenuOffsetRight >= maxWidth ) {
								$this.removeClass( 'inverse-side' );
								$this.find( '.jet-custom-nav__sub' ).removeClass( 'inverse-side' );
							}
						}
					} );
				}
			}

			setSubMenuPosition();
			$( window ).on( 'resize.JetCustomMenu orientationchange.JetCustomMenu', setSubMenuPosition );

			var initMaxMegaMenuWidth = false;

			function setMaxMegaMenuWidth(){
				var megaMenu = $( '.jet-custom-nav__mega-sub', $target ),
					$body    = $( 'body' ),
					maxWidth = $body.outerWidth( true ),
					isMobile = 'mobile' === elementor.getCurrentDeviceMode();

				if ( initMaxMegaMenuWidth ) {
					megaMenu.css( {
						'maxWidth': ''
					} );

					initMaxMegaMenuWidth = false;
				}

				if ( isMobile ) {
					return;
				}

				if ( megaMenu[0] ) {
					megaMenu.each( function() {
						var $this = $( this ),
							megaMenuTranslateX = $this.css( 'transform' ).replace( /,/g, "" ).split( " " )[4] || 0,
							megaMenuOffsetLeft = $this.offset().left - megaMenuTranslateX,
							megaMenuOffsetRight = megaMenuOffsetLeft + $this.outerWidth( true ),
							megaMenuPosition = $this.closest( '.jet-custom-nav' ).hasClass( 'jet-custom-nav--dropdown-left-side' ) ? 'left-side' : 'right-side';

						if ( 'right-side' === megaMenuPosition ) {
							if ( megaMenuOffsetRight >= maxWidth ) {
								$this.css({
									'maxWidth': maxWidth - megaMenuOffsetLeft - 10
								});

								initMaxMegaMenuWidth = true;
							}
						} else {
							if ( megaMenuOffsetLeft < 0 ) {
								$this.css({
									'maxWidth': megaMenuOffsetRight - 10
								});

								initMaxMegaMenuWidth = true;
							}
						}
					} );
				}
			}

			setMaxMegaMenuWidth();
			$( window ).on( 'resize.JetCustomMenu orientationchange.JetCustomMenu', setMaxMegaMenuWidth );

		},

		widgetMobileMenu: function( $scope ) {
			let $target        = $scope.find( '.jet-mobile-menu' ),
				menuInstanceId = $target.attr( 'id' ),
				menuId         = $target.data( 'menu-id' ) || false,
				menuOptions    = $target.data( 'menu-options' ) || {};

			if ( ! $target[0] ) {
				return;
			}

			window.jetMenu.createMobileRenderInstance( menuInstanceId, menuId, menuOptions );
		},

		/**
		 * Specific check for iPad Pro\Air in Safari with touch input,
		 * only if the cookie has not been set yet.
		 *
		 * @return {boolean}
		 */
		shouldSetIpadProCookie: function() {
			const isSafari  = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
			const isMacLike = navigator.userAgent.includes( 'Macintosh' );
			const hasTouch  = 'ontouchend' in window || navigator.maxTouchPoints > 1;

			const cookieNotSet = document.cookie.indexOf( 'is_ipad_pro=true' ) === -1;

			return isSafari && isMacLike && hasTouch && cookieNotSet;
		},

		/**
		 * Mobile and tablet check funcion.
		 *
		 * @return {boolean} Mobile Status
		 */
		mobileAndTabletcheck: function() {
			var check = false;

			(function(a){if(/(android|bb\d+|meego).+mobile|avantgo|bada\/|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od)|iris|kindle|lge |maemo|midp|mmp|mobile.+firefox|netfront|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\/|plucker|pocket|psp|series(4|6)0|symbian|treo|up\.(browser|link)|vodafone|wap|windows ce|xda|xiino|android|ipad|playbook|silk/i.test(a)||/1207|6310|6590|3gso|4thp|50[1-6]i|770s|802s|a wa|abac|ac(er|oo|s\-)|ai(ko|rn)|al(av|ca|co)|amoi|an(ex|ny|yw)|aptu|ar(ch|go)|as(te|us)|attw|au(di|\-m|r |s )|avan|be(ck|ll|nq)|bi(lb|rd)|bl(ac|az)|br(e|v)w|bumb|bw\-(n|u)|c55\/|capi|ccwa|cdm\-|cell|chtm|cldc|cmd\-|co(mp|nd)|craw|da(it|ll|ng)|dbte|dc\-s|devi|dica|dmob|do(c|p)o|ds(12|\-d)|el(49|ai)|em(l2|ul)|er(ic|k0)|esl8|ez([4-7]0|os|wa|ze)|fetc|fly(\-|_)|g1 u|g560|gene|gf\-5|g\-mo|go(\.w|od)|gr(ad|un)|haie|hcit|hd\-(m|p|t)|hei\-|hi(pt|ta)|hp( i|ip)|hs\-c|ht(c(\-| |_|a|g|p|s|t)|tp)|hu(aw|tc)|i\-(20|go|ma)|i230|iac( |\-|\/)|ibro|idea|ig01|ikom|im1k|inno|ipaq|iris|ja(t|v)a|jbro|jemu|jigs|kddi|keji|kgt( |\/)|klon|kpt |kwc\-|kyo(c|k)|le(no|xi)|lg( g|\/(k|l|u)|50|54|\-[a-w])|libw|lynx|m1\-w|m3ga|m50\/|ma(te|ui|xo)|mc(01|21|ca)|m\-cr|me(rc|ri)|mi(o8|oa|ts)|mmef|mo(01|02|bi|de|do|t(\-| |o|v)|zz)|mt(50|p1|v )|mwbp|mywa|n10[0-2]|n20[2-3]|n30(0|2)|n50(0|2|5)|n7(0(0|1)|10)|ne((c|m)\-|on|tf|wf|wg|wt)|nok(6|i)|nzph|o2im|op(ti|wv)|oran|owg1|p800|pan(a|d|t)|pdxg|pg(13|\-([1-8]|c))|phil|pire|pl(ay|uc)|pn\-2|po(ck|rt|se)|prox|psio|pt\-g|qa\-a|qc(07|12|21|32|60|\-[2-7]|i\-)|qtek|r380|r600|raks|rim9|ro(ve|zo)|s55\/|sa(ge|ma|mm|ms|ny|va)|sc(01|h\-|oo|p\-)|sdk\/|se(c(\-|0|1)|47|mc|nd|ri)|sgh\-|shar|sie(\-|m)|sk\-0|sl(45|id)|sm(al|ar|b3|it|t5)|so(ft|ny)|sp(01|h\-|v\-|v )|sy(01|mb)|t2(18|50)|t6(00|10|18)|ta(gt|lk)|tcl\-|tdg\-|tel(i|m)|tim\-|t\-mo|to(pl|sh)|ts(70|m\-|m3|m5)|tx\-9|up(\.b|g1|si)|utst|v400|v750|veri|vi(rg|te)|vk(40|5[0-3]|\-v)|vm40|voda|vulc|vx(52|53|60|61|70|80|81|83|85|98)|w3c(\-| )|webc|whit|wi(g |nc|nw)|wmlb|wonu|x700|yas\-|your|zeto|zte\-/i.test(a.substr(0,4))) check = true;})(navigator.userAgent||navigator.vendor||window.opera);

			return check;
		}
	};

	$( window ).on( 'elementor/frontend/init', JetMenuWidget.init );

}( jQuery, window.elementorFrontend ) );
